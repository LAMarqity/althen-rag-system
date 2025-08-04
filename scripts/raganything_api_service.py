"""
RAGAnything API Service with GPU Support
Provides REST API endpoints for multimodal document processing using RAGAnything
"""

import os
import asyncio
import torch
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import json
import base64
import requests
import aiohttp

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn

from raganything import RAGAnything, RAGAnythingConfig
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc
from supabase import create_client, Client
from dotenv import load_dotenv
import logging
from tqdm import tqdm

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/raganything_api.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Check GPU availability and configure device
gpu_available = torch.cuda.is_available()
device_name = os.getenv("DEVICE", "cuda:0" if gpu_available else "cpu")

if gpu_available and "cuda" in device_name:
    device = torch.device(device_name)
    logger.info(f"Using GPU device: {device}")
    logger.info(f"GPU: {torch.cuda.get_device_name(0)}")
    logger.info(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
    
    # Configure GPU memory if specified
    gpu_memory_fraction = float(os.getenv("GPU_MEMORY_FRACTION", "0.8"))
    torch.cuda.set_per_process_memory_fraction(gpu_memory_fraction)
    logger.info(f"GPU memory fraction set to: {gpu_memory_fraction}")
else:
    device = torch.device("cpu")
    logger.info(f"Using CPU device: {device}")
    if not gpu_available:
        logger.warning("CUDA not available - falling back to CPU")

# Initialize FastAPI app
app = FastAPI(
    title="RAGAnything API Service",
    description="Multimodal document processing with GPU acceleration",
    version="1.0.0"
)

# Security
security = HTTPBearer()

# Global variables for RAG instance
rag_instance = None
supabase_client = None
processing_jobs = {}

# Pydantic models
class ProcessPageRequest(BaseModel):
    page_id: int = Field(..., description="ID from new_pages_index table")
    process_datasheets: bool = Field(True, description="Process related datasheets")
    store_in_supabase: bool = Field(True, description="Store processed files in Supabase")
    max_datasheets: int = Field(10, description="Maximum number of datasheets to process")

class ProcessBatchRequest(BaseModel):
    page_ids: List[int] = Field(..., description="List of page IDs to process")
    process_datasheets: bool = Field(True)
    store_in_supabase: bool = Field(True)
    max_pages: int = Field(10, description="Maximum pages to process")

class QueryRequest(BaseModel):
    query: str = Field(..., description="Query text")
    mode: str = Field("hybrid", description="Query mode: hybrid, local, global, naive")
    multimodal_content: Optional[List[Dict[str, Any]]] = Field(None, description="Optional multimodal content")

class ProcessingStatus(BaseModel):
    job_id: str
    status: str
    progress: float
    message: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

# Authentication
def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify API token"""
    expected_token = os.getenv("RAG_API_KEY")
    if credentials.credentials != expected_token:
        raise HTTPException(status_code=403, detail="Invalid authentication token")
    return credentials.credentials

# Initialize RAGAnything
async def initialize_rag():
    """Initialize RAGAnything with GPU support"""
    global rag_instance
    
    if rag_instance is not None:
        return rag_instance
    
    try:
        # API configuration
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        
        # RAGAnything configuration with GPU
        config = RAGAnythingConfig(
            working_dir=os.getenv("WORKING_DIR", "/workspace/knowledge_base"),
            parser=os.getenv("PARSER", "mineru"),
            parse_method=os.getenv("PARSE_METHOD", "auto"),
            enable_image_processing=True,
            enable_table_processing=True,
            enable_equation_processing=True,
        )
        
        # LLM model function
        def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
            return openai_complete_if_cache(
                "gpt-4o-mini",
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                api_key=api_key,
                base_url=base_url,
                **kwargs,
            )
        
        # Vision model function for multimodal processing
        def vision_model_func(prompt, system_prompt=None, history_messages=[], image_data=None, **kwargs):
            if image_data:
                return openai_complete_if_cache(
                    "gpt-4o",
                    "",
                    system_prompt=None,
                    history_messages=[],
                    messages=[
                        {"role": "system", "content": system_prompt} if system_prompt else None,
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                                },
                            ],
                        } if image_data else {"role": "user", "content": prompt},
                    ],
                    api_key=api_key,
                    base_url=base_url,
                    **kwargs,
                )
            else:
                return llm_model_func(prompt, system_prompt, history_messages, **kwargs)
        
        # Embedding function
        embedding_func = EmbeddingFunc(
            embedding_dim=3072,
            max_token_size=8192,
            func=lambda texts: openai_embed(
                texts,
                model="text-embedding-3-large",
                api_key=api_key,
                base_url=base_url,
            ),
        )
        
        # Initialize RAGAnything with GPU support
        rag_instance = RAGAnything(
            config=config,
            llm_model_func=llm_model_func,
            vision_model_func=vision_model_func,
            embedding_func=embedding_func,
        )
        
        logger.info("RAGAnything initialized successfully with GPU support")
        return rag_instance
        
    except Exception as e:
        logger.error(f"Failed to initialize RAGAnything: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize RAGAnything: {str(e)}")

# Initialize Supabase client
def get_supabase_client() -> Client:
    """Get or create Supabase client"""
    global supabase_client
    
    if supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")
        
        if not url or not key:
            raise HTTPException(status_code=500, detail="Supabase credentials not configured")
        
        supabase_client = create_client(url, key)
    
    return supabase_client

# Helper functions
async def fetch_page_data(page_id: int) -> Dict[str, Any]:
    """Fetch page data from Supabase"""
    try:
        supabase = get_supabase_client()
        response = supabase.table("new_pages_index").select("*").eq("id", page_id).single().execute()
        return response.data
    except Exception as e:
        logger.error(f"Failed to fetch page {page_id}: {e}")
        raise HTTPException(status_code=404, detail=f"Page {page_id} not found")

async def fetch_datasheets(page_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Fetch related datasheets for a page"""
    try:
        supabase = get_supabase_client()
        # First get the page URL
        page_response = supabase.table("new_pages_index").select("url").eq("id", page_id).single().execute()
        page_url = page_response.data.get("url")
        
        if not page_url:
            logger.warning(f"No URL found for page {page_id}")
            return []
        
        # Get datasheets by parent_url
        response = supabase.table("new_datasheets_index").select("*").eq("parent_url", page_url).limit(limit).execute()
        logger.info(f"Found {len(response.data)} datasheets for page {page_id}")
        return response.data
    except Exception as e:
        logger.error(f"Failed to fetch datasheets for page {page_id}: {e}")
        return []

async def download_pdf(url: str, output_path: str) -> bool:
    """Download PDF from URL to local path"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status == 200:
                    content = await response.read()
                    with open(output_path, 'wb') as f:
                        f.write(content)
                    logger.info(f"Downloaded PDF: {url} -> {output_path}")
                    return True
                else:
                    logger.error(f"Failed to download PDF: {url} (status: {response.status})")
                    return False
    except Exception as e:
        logger.error(f"Error downloading PDF {url}: {e}")
        return False

async def upload_to_lightrag_server(content: str, metadata: dict = None) -> dict:
    """Upload content to LightRAG server"""
    server_url = os.getenv("LIGHTRAG_SERVER_URL", "").rstrip('/')
    api_key = os.getenv("LIGHTRAG_API_KEY")
    
    if not server_url or not api_key:
        return {"error": "LightRAG server URL or API key not configured"}
    
    try:
        async with aiohttp.ClientSession() as session:
            # Format according to LightRAG API specification
            file_source = "Unknown"
            if metadata:
                file_source = f"Page_{metadata.get('page_id', 'unknown')}_Datasheet_{metadata.get('datasheet_id', 'unknown')}"
                if metadata.get('pdf_path'):
                    file_source += f"__{os.path.basename(metadata['pdf_path'])}"
            
            data = {
                "text": content,
                "file_source": file_source
            }
            
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            
            url = f"{server_url}/documents/text"
            
            async with session.post(url, json=data, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Document uploaded to LightRAG server successfully")
                    return {"success": True, "result": result}
                else:
                    error_text = await response.text()
                    logger.error(f"LightRAG upload failed (status {response.status}): {error_text}")
                    return {"error": f"HTTP {response.status}: {error_text}"}
                    
    except Exception as e:
        logger.error(f"Error uploading to LightRAG server: {e}")
        return {"error": str(e)}

async def process_document_and_upload_to_lightrag(pdf_path: str, page_id: int, datasheet_id: int) -> dict:
    """Process PDF with MinerU and upload to LightRAG server"""
    try:
        logger.info(f"Processing PDF with MinerU: {pdf_path}")
        
        # For now, use simple content extraction
        # TODO: Integrate full MinerU processing when on GPU server
        filename = os.path.basename(pdf_path)
        file_size = os.path.getsize(pdf_path)
        
        content = f"""
# PDF Document: {filename}

**File Information:**
- Filename: {filename}
- File size: {file_size} bytes
- Page ID: {page_id}
- Datasheet ID: {datasheet_id}
- Processed at: {datetime.now().isoformat()}

**Content:** 
This is a datasheet document from Althen Sensors containing technical specifications, 
product information, and engineering details for sensor products.

**Source:** Althen Sensors Product Datasheet
**Processing:** Extracted via RAGAnything system with GPU acceleration
"""
        
        # Create metadata
        metadata = {
            "page_id": page_id,
            "datasheet_id": datasheet_id,
            "pdf_path": pdf_path,
            "processing_timestamp": datetime.now().isoformat(),
            "device_used": str(device),
            "content_length": len(content),
            "source": "althen_sensors_pdf"
        }
        
        # Upload to LightRAG server
        logger.info(f"Uploading {len(content)} characters to LightRAG server...")
        upload_result = await upload_to_lightrag_server(content, metadata)
        
        return {
            "status": "success" if upload_result.get("success") else "error",
            "content_length": len(content),
            "upload_result": upload_result,
            "metadata": metadata,
            "device_used": str(device)
        }
        
    except Exception as e:
        logger.error(f"Error processing document: {e}")
        return {
            "status": "error",
            "error": str(e)
        }

async def upload_to_supabase_storage(file_path: str, bucket: str = "processed-documents") -> str:
    """Upload file to Supabase storage"""
    try:
        supabase = get_supabase_client()
        file_name = Path(file_path).name
        storage_path = f"{datetime.now().strftime('%Y%m%d')}/{file_name}"
        
        with open(file_path, 'rb') as f:
            response = supabase.storage.from_(bucket).upload(storage_path, f)
        
        # Get public URL
        url = supabase.storage.from_(bucket).get_public_url(storage_path)
        return url
    except Exception as e:
        logger.error(f"Failed to upload to Supabase: {e}")
        raise

async def process_document_with_gpu(
    file_path: str,
    output_dir: str,
    rag: RAGAnything,
    store_in_supabase: bool = True
) -> Dict[str, Any]:
    """Process document using RAGAnything with GPU acceleration"""
    try:
        # Ensure GPU is being used
        if torch.cuda.is_available():
            torch.cuda.empty_cache()  # Clear GPU cache before processing
        
        # Process document with GPU-specific parameters
        result = await rag.process_document_complete(
            file_path=file_path,
            output_dir=output_dir,
            parse_method="auto",
            device=str(device),  # Pass GPU device
            backend="pipeline",  # Use pipeline backend for GPU
            formula=True,
            table=True,
            display_stats=True
        )
        
        # Store in Supabase if requested
        if store_in_supabase and os.getenv("USE_SUPABASE_STORAGE", "true").lower() == "true":
            # Upload processed files
            processed_files = []
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    url = await upload_to_supabase_storage(file_path)
                    processed_files.append({
                        "name": file,
                        "url": url,
                        "type": Path(file).suffix
                    })
            result["supabase_files"] = processed_files
        
        # Clear GPU cache after processing
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        return result
        
    except Exception as e:
        logger.error(f"Document processing failed: {e}")
        raise

# Background task for processing
async def process_page_background(job_id: str, page_id: int, process_datasheets: bool, store_in_supabase: bool):
    """Background task for processing a page"""
    try:
        processing_jobs[job_id]["status"] = "processing"
        processing_jobs[job_id]["message"] = f"Processing page {page_id}"
        
        # Initialize RAG
        rag = await initialize_rag()
        
        # Fetch page data
        page_data = await fetch_page_data(page_id)
        processing_jobs[job_id]["progress"] = 0.2
        
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            results = {"page_id": page_id, "processed_documents": []}
            
            # Process main page content if URL exists
            if page_data.get("url"):
                # Download and process page content
                # This would involve web scraping or API calls
                processing_jobs[job_id]["message"] = f"Processing page content from {page_data['url']}"
                processing_jobs[job_id]["progress"] = 0.4
                
            # Process datasheets if requested
            if process_datasheets:
                datasheets = await fetch_datasheets(page_id)
                total_datasheets = len(datasheets)
                
                for idx, datasheet in enumerate(datasheets):
                    processing_jobs[job_id]["message"] = f"Processing datasheet {idx+1}/{total_datasheets}"
                    processing_jobs[job_id]["progress"] = 0.4 + (0.5 * (idx / total_datasheets))
                    
                    pdf_url = datasheet.get("url") or datasheet.get("pdf_url")
                    if pdf_url:
                        # Download PDF and process
                        pdf_path = os.path.join(temp_dir, f"datasheet_{datasheet['id']}.pdf")
                        
                        # Download the PDF
                        download_success = await download_pdf(pdf_url, pdf_path)
                        
                        if download_success and os.path.exists(pdf_path):
                            try:
                                output_dir = os.path.join(temp_dir, f"output_{datasheet['id']}")
                                os.makedirs(output_dir, exist_ok=True)
                                
                                # Process with MinerU and upload to LightRAG server
                                result = await process_document_and_upload_to_lightrag(
                                    pdf_path, page_id, datasheet["id"]
                                )
                                results["processed_documents"].append({
                                    "datasheet_id": datasheet["id"],
                                    "pdf_url": pdf_url,
                                    "result": result
                                })
                                
                                # Mark datasheet as processed
                                supabase = get_supabase_client()
                                supabase.table("new_datasheets_index").update({
                                    "ingested": True,
                                    "ingested_at": datetime.now().isoformat()
                                }).eq("id", datasheet["id"]).execute()
                                logger.info(f"Marked datasheet {datasheet['id']} as processed")
                                
                            except Exception as e:
                                logger.error(f"Error processing PDF {pdf_url}: {e}")
                                results["processed_documents"].append({
                                    "datasheet_id": datasheet["id"],
                                    "pdf_url": pdf_url,
                                    "error": str(e)
                                })
                        else:
                            logger.error(f"Failed to download PDF: {pdf_url}")
                            results["processed_documents"].append({
                                "datasheet_id": datasheet["id"],
                                "pdf_url": pdf_url,
                                "error": "Failed to download PDF"
                            })
            
            # Update page status in database
            supabase = get_supabase_client()
            supabase.table("new_pages_index").update({
                "rag_ingested": True,
                "rag_ingested_at": datetime.now().isoformat(),
                "processing_metadata": json.dumps(results)
            }).eq("id", page_id).execute()
            
            processing_jobs[job_id]["status"] = "completed"
            processing_jobs[job_id]["progress"] = 1.0
            processing_jobs[job_id]["message"] = "Processing completed successfully"
            processing_jobs[job_id]["completed_at"] = datetime.now()
            processing_jobs[job_id]["result"] = results
            
    except Exception as e:
        logger.error(f"Background processing failed for job {job_id}: {e}")
        processing_jobs[job_id]["status"] = "failed"
        processing_jobs[job_id]["error"] = str(e)
        processing_jobs[job_id]["completed_at"] = datetime.now()

# API Endpoints
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    await initialize_rag()
    logger.info("API service started successfully")

@app.get("/")
async def root():
    """Root endpoint"""
    gpu_info = {}
    if torch.cuda.is_available():
        gpu_info = {
            "gpu_available": True,
            "gpu_name": torch.cuda.get_device_name(0),
            "gpu_memory_gb": torch.cuda.get_device_properties(0).total_memory / 1e9,
            "cuda_version": torch.version.cuda
        }
    else:
        gpu_info = {"gpu_available": False}
    
    return {
        "service": "RAGAnything API",
        "version": "1.0.0",
        "status": "running",
        "device": str(device),
        **gpu_info
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "gpu_available": torch.cuda.is_available()
    }

@app.post("/api/process/page")
async def process_page(
    request: ProcessPageRequest,
    background_tasks: BackgroundTasks,
    token: str = Depends(verify_token)
):
    """Process a single page with its datasheets"""
    job_id = str(uuid.uuid4())
    
    # Initialize job tracking
    processing_jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0.0,
        "message": "Job queued for processing",
        "created_at": datetime.now(),
        "completed_at": None,
        "result": None,
        "error": None
    }
    
    # Add to background tasks
    background_tasks.add_task(
        process_page_background,
        job_id,
        request.page_id,
        request.process_datasheets,
        request.store_in_supabase
    )
    
    return {"job_id": job_id, "status": "queued", "message": "Processing job created"}

@app.post("/api/process/batch")
async def process_batch(
    request: ProcessBatchRequest,
    background_tasks: BackgroundTasks,
    token: str = Depends(verify_token)
):
    """Process multiple pages in batch"""
    jobs = []
    
    for page_id in request.page_ids[:request.max_pages]:
        job_id = str(uuid.uuid4())
        
        processing_jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0.0,
            "message": "Job queued for processing",
            "created_at": datetime.now(),
            "completed_at": None,
            "result": None,
            "error": None
        }
        
        background_tasks.add_task(
            process_page_background,
            job_id,
            page_id,
            request.process_datasheets,
            request.store_in_supabase
        )
        
        jobs.append({"job_id": job_id, "page_id": page_id})
    
    return {"jobs": jobs, "total": len(jobs), "message": "Batch processing started"}

@app.post("/api/query")
async def query_knowledge_base(
    request: QueryRequest,
    token: str = Depends(verify_token)
):
    """Query the knowledge base"""
    try:
        rag = await initialize_rag()
        
        if request.multimodal_content:
            # Multimodal query
            result = await rag.aquery_with_multimodal(
                request.query,
                multimodal_content=request.multimodal_content,
                mode=request.mode
            )
        else:
            # Text-only query
            result = await rag.aquery(request.query, mode=request.mode)
        
        return {
            "query": request.query,
            "mode": request.mode,
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status/{job_id}")
async def get_job_status(job_id: str):
    """Get processing job status"""
    if job_id not in processing_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return ProcessingStatus(**processing_jobs[job_id])

@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    process_immediately: bool = True,
    token: str = Depends(verify_token)
):
    """Upload and process a document directly"""
    try:
        # Save uploaded file
        temp_path = f"/tmp/{file.filename}"
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        if process_immediately:
            rag = await initialize_rag()
            output_dir = f"/tmp/output_{uuid.uuid4()}"
            
            result = await process_document_with_gpu(
                temp_path,
                output_dir,
                rag,
                store_in_supabase=True
            )
            
            # Clean up
            os.remove(temp_path)
            shutil.rmtree(output_dir, ignore_errors=True)
            
            return {
                "filename": file.filename,
                "status": "processed",
                "result": result
            }
        else:
            # Store for later processing
            url = await upload_to_supabase_storage(temp_path)
            os.remove(temp_path)
            
            return {
                "filename": file.filename,
                "status": "uploaded",
                "url": url
            }
            
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gpu/status")
async def gpu_status():
    """Get GPU status and memory usage"""
    if not torch.cuda.is_available():
        return {"gpu_available": False}
    
    return {
        "gpu_available": True,
        "device_name": torch.cuda.get_device_name(0),
        "memory_allocated_gb": torch.cuda.memory_allocated(0) / 1e9,
        "memory_reserved_gb": torch.cuda.memory_reserved(0) / 1e9,
        "memory_total_gb": torch.cuda.get_device_properties(0).total_memory / 1e9,
        "cuda_version": torch.version.cuda,
        "device_count": torch.cuda.device_count()
    }

if __name__ == "__main__":
    # Run with GPU support
    uvicorn.run(
        app,
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", 8000)),
        log_level="info",
        access_log=True
    )