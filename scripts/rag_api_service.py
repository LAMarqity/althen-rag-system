#!/usr/bin/env python3
"""
RAG API Service - FastAPI service for processing pages to LightRAG
Supports both local and cloud deployment with GPU access for MinerU processing
"""

import asyncio
import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Security, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("[OK] Environment variables loaded")
except ImportError:
    print("[WARNING] python-dotenv not available, using system environment variables")

# Import our LightRAG client
from lightrag_server_client import LightRAGServerClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API Configuration
API_KEY = os.getenv("RAG_API_KEY", "your-secure-api-key-here")
API_HOST = os.getenv("RAG_API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("RAG_API_PORT", "8080"))
LIGHTRAG_SERVER_URL = os.getenv("LIGHTRAG_SERVER_URL", "http://localhost:8020")

# Security
security = HTTPBearer()

# Global client instance
rag_client: Optional[LightRAGServerClient] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global rag_client
    
    # Startup
    logger.info("[START] Starting RAG API Service...")
    try:
        rag_client = LightRAGServerClient(LIGHTRAG_SERVER_URL)
        logger.info(f"[OK] LightRAG client initialized (Server: {LIGHTRAG_SERVER_URL})")
        
        # Test connection
        if rag_client.test_lightrag_server_connection():
            logger.info("[OK] LightRAG server connection successful")
        else:
            logger.warning("[WARNING] LightRAG server connection failed - will retry on requests")
            
    except Exception as e:
        logger.error(f"[ERROR] Failed to initialize RAG client: {e}")
        rag_client = None
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down RAG API Service...")

# Create FastAPI app
app = FastAPI(
    title="RAG API Service",
    description="API service for processing pages with RAGAnything pipeline to LightRAG",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure as needed for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response Models
class ProcessPageRequest(BaseModel):
    page_id: int = Field(..., description="Page ID from new_pages_index table")
    fast_mode: bool = Field(default=True, description="Use fast mode for processing (recommended)")
    force_reprocess: bool = Field(default=False, description="Force reprocessing even if already ingested")

class ProcessPageResponse(BaseModel):
    success: bool
    page_id: int
    message: str
    processing_time: Optional[float] = None
    results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class ProcessStatusResponse(BaseModel):
    page_id: int
    status: str
    details: Optional[Dict[str, Any]] = None

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    lightrag_connected: bool
    version: str

# Authentication
async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verify API key authentication"""
    if credentials.credentials != API_KEY:
        raise HTTPException(
            status_code=401, 
            detail="Invalid API key"
        )
    return credentials.credentials

# API Endpoints

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    lightrag_connected = False
    
    if rag_client:
        try:
            lightrag_connected = rag_client.test_lightrag_server_connection()
        except Exception:
            pass
    
    return HealthResponse(
        status="healthy" if lightrag_connected else "degraded",
        timestamp=datetime.now().isoformat(),
        lightrag_connected=lightrag_connected,
        version="1.0.0"
    )

@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "RAG API Service",
        "version": "1.0.0",
        "description": "API service for processing pages with RAGAnything pipeline to LightRAG",
        "endpoints": {
            "health": "GET /health - Health check",
            "process_page": "POST /process-page - Process a specific page by ID",
            "status": "GET /status/{page_id} - Get processing status",
            "docs": "GET /docs - OpenAPI documentation"
        },
        "authentication": "Bearer token required"
    }

@app.post("/process-page", response_model=ProcessPageResponse)
async def process_page(
    request: ProcessPageRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """
    Process a specific page by ID through the complete RAG pipeline:
    1. Web content scraping
    2. PDF processing with MinerU 
    3. Image upload to Supabase Storage
    4. Content ingestion to LightRAG
    """
    start_time = datetime.now()
    
    if not rag_client:
        raise HTTPException(
            status_code=503,
            detail="RAG client not available - service initialization failed"
        )
    
    try:
        logger.info(f"🎯 Processing page {request.page_id} (fast_mode={request.fast_mode})")
        
        # Process the page
        result = await rag_client.process_specific_page_to_lightrag(
            request.page_id,
            fast_mode=request.fast_mode
        )
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        if "error" in result:
            return ProcessPageResponse(
                success=False,
                page_id=request.page_id,
                message=f"Processing failed: {result['error']}",
                processing_time=processing_time,
                error=result["error"]
            )
        
        # Success response
        success = result.get("successful", 0) > 0
        message = f"Page {request.page_id} processed successfully" if success else f"Page {request.page_id} processing completed with issues"
        
        return ProcessPageResponse(
            success=success,
            page_id=request.page_id,
            message=message,
            processing_time=processing_time,
            results=result
        )
        
    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"[ERROR] Error processing page {request.page_id}: {e}")
        
        return ProcessPageResponse(
            success=False,
            page_id=request.page_id,
            message=f"Internal error processing page {request.page_id}",
            processing_time=processing_time,
            error=str(e)
        )

@app.get("/status/{page_id}", response_model=ProcessStatusResponse)
async def get_page_status(
    page_id: int,
    api_key: str = Depends(verify_api_key)
):
    """Get processing status for a specific page"""
    if not rag_client:
        raise HTTPException(
            status_code=503,
            detail="RAG client not available"
        )
    
    try:
        # Check if page exists and is ingested
        page_response = rag_client.supabase.table("new_pages_index").select("id,url,ingested,created_at").eq("id", page_id).execute()
        
        if not page_response.data:
            raise HTTPException(
                status_code=404,
                detail=f"Page {page_id} not found"
            )
        
        page = page_response.data[0]
        
        return ProcessStatusResponse(
            page_id=page_id,
            status="ingested" if page.get("ingested") else "pending",
            details={
                "url": page.get("url"),
                "created_at": page.get("created_at"),
                "ingested": page.get("ingested", False)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] Error checking status for page {page_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error checking page status: {str(e)}"
        )

@app.post("/batch-process")
async def batch_process_pages(
    page_ids: list[int],
    fast_mode: bool = True,
    api_key: str = Depends(verify_api_key)
):
    """Process multiple pages in batch (for CRON jobs)"""
    if not rag_client:
        raise HTTPException(
            status_code=503,
            detail="RAG client not available"
        )
    
    if len(page_ids) > 10:
        raise HTTPException(
            status_code=400,
            detail="Batch processing limited to 10 pages at a time"
        )
    
    results = []
    start_time = datetime.now()
    
    for page_id in page_ids:
        try:
            logger.info(f"[BATCH] Batch processing page {page_id}")
            result = await rag_client.process_specific_page_to_lightrag(
                page_id,
                fast_mode=fast_mode
            )
            results.append({
                "page_id": page_id,
                "success": "error" not in result,
                "result": result
            })
            
            # Small delay between pages
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"[ERROR] Error processing page {page_id} in batch: {e}")
            results.append({
                "page_id": page_id,
                "success": False,
                "error": str(e)
            })
    
    processing_time = (datetime.now() - start_time).total_seconds()
    successful = len([r for r in results if r["success"]])
    
    return {
        "batch_id": f"batch_{int(start_time.timestamp())}",
        "total_pages": len(page_ids),
        "successful": successful,
        "failed": len(page_ids) - successful,
        "processing_time": processing_time,
        "results": results
    }

# Main entry point
if __name__ == "__main__":
    logger.info(f"[START] Starting RAG API Service on {API_HOST}:{API_PORT}")
    logger.info(f"📡 LightRAG Server: {LIGHTRAG_SERVER_URL}")
    logger.info(f"🔐 API Key configured: {'Yes' if API_KEY != 'your-secure-api-key-here' else 'No (using default)'}")
    
    uvicorn.run(
        "rag_api_service:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,  # Set to True for development
        log_level="info"
    )