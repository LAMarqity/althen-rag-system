#!/usr/bin/env python3
"""
LightRAG Server Integration
Processes documents and uploads to remote LightRAG server
"""

import os
import asyncio
import aiohttp
import tempfile
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

# Load environment
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LightRAGServerClient:
    def __init__(self):
        self.server_url = os.getenv("LIGHTRAG_SERVER_URL", "https://lightrag-latest-hyhs.onrender.com/")
        self.api_key = os.getenv("LIGHTRAG_API_KEY")
        
        if not self.server_url or not self.api_key:
            raise ValueError("LIGHTRAG_SERVER_URL and LIGHTRAG_API_KEY are required")
        
        # Remove trailing slash
        self.server_url = self.server_url.rstrip('/')
        
        logger.info(f"LightRAG Server: {self.server_url}")
    
    async def upload_document(self, content: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Upload document content to LightRAG server"""
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    "content": content,
                    "metadata": metadata or {}
                }
                
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                url = f"{self.server_url}/insert"
                
                async with session.post(url, json=data, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Document uploaded successfully: {result}")
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(f"Upload failed (status {response.status}): {error_text}")
                        return {"error": f"HTTP {response.status}: {error_text}"}
                        
        except Exception as e:
            logger.error(f"Error uploading to LightRAG server: {e}")
            return {"error": str(e)}
    
    async def query_server(self, query: str, mode: str = "hybrid") -> Dict[str, Any]:
        """Query the LightRAG server"""
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    "query": query,
                    "mode": mode
                }
                
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                url = f"{self.server_url}/query"
                
                async with session.post(url, json=data, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Query successful: {query[:50]}...")
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(f"Query failed (status {response.status}): {error_text}")
                        return {"error": f"HTTP {response.status}: {error_text}"}
                        
        except Exception as e:
            logger.error(f"Error querying LightRAG server: {e}")
            return {"error": str(e)}
    
    async def check_server_status(self) -> Dict[str, Any]:
        """Check server status"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}"
                }
                
                url = f"{self.server_url}/status"
                
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info("Server status check successful")
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(f"Status check failed (status {response.status}): {error_text}")
                        return {"error": f"HTTP {response.status}: {error_text}"}
                        
        except Exception as e:
            logger.error(f"Error checking server status: {e}")
            return {"error": str(e)}

async def process_document_with_mineru_and_upload(
    pdf_path: str,
    page_id: int,
    datasheet_id: int,
    lightrag_client: LightRAGServerClient
) -> Dict[str, Any]:
    """Process PDF with MinerU and upload to LightRAG server"""
    
    try:
        # Import MinerU processing
        from magic_pdf.pipe.UNIPipe import UNIPipe
        from magic_pdf.model.pdf_extract_kit.pdf_extract_kit import PDFExtractKit
        import torch
        
        logger.info(f"Processing PDF with MinerU: {pdf_path}")
        
        # Check if CUDA is available
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        logger.info(f"Using device: {device}")
        
        # Create output directory
        with tempfile.TemporaryDirectory() as temp_output_dir:
            output_dir = Path(temp_output_dir)
            
            # Initialize PDFExtractKit with GPU support if available
            pdf_extract_kit = PDFExtractKit(
                device=device,
                enable_image_processing=os.getenv("ENABLE_IMAGE_PROCESSING", "true").lower() == "true",
                enable_table_processing=os.getenv("ENABLE_TABLE_PROCESSING", "true").lower() == "true",
                enable_equation_processing=os.getenv("ENABLE_EQUATION_PROCESSING", "true").lower() == "true"
            )
            
            # Process with UNIPipe
            pipe = UNIPipe(
                pdf_path=pdf_path,
                output_dir=str(output_dir),
                extract_kit=pdf_extract_kit
            )
            
            # Execute processing
            result = pipe.pipe_parse()
            
            logger.info("MinerU processing completed")
            
            # Extract processed content
            content_parts = []
            
            # Get markdown content if available
            markdown_files = list(output_dir.glob("**/*.md"))
            for md_file in markdown_files:
                try:
                    with open(md_file, 'r', encoding='utf-8') as f:
                        md_content = f.read()
                        content_parts.append(f"# Document: {md_file.name}\n\n{md_content}")
                except Exception as e:
                    logger.warning(f"Could not read markdown file {md_file}: {e}")
            
            # Get JSON content lists if available
            json_files = list(output_dir.glob("**/*_content_list.json"))
            for json_file in json_files:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        json_content = json.load(f)
                        # Extract text content from JSON structure
                        if isinstance(json_content, list):
                            for item in json_content:
                                if isinstance(item, dict) and 'text' in item:
                                    content_parts.append(item['text'])
                except Exception as e:
                    logger.warning(f"Could not read JSON file {json_file}: {e}")
            
            # Combine all content
            full_content = "\n\n".join(content_parts) if content_parts else "No content extracted"
            
            # Create metadata
            metadata = {
                "page_id": page_id,
                "datasheet_id": datasheet_id,
                "pdf_path": pdf_path,
                "processing_timestamp": datetime.now().isoformat(),
                "device_used": device,
                "content_length": len(full_content),
                "source": "althen_sensors_pdf"
            }
            
            # Upload to LightRAG server
            logger.info(f"Uploading {len(full_content)} characters to LightRAG server...")
            upload_result = await lightrag_client.upload_document(full_content, metadata)
            
            return {
                "status": "success",
                "content_length": len(full_content),
                "upload_result": upload_result,
                "metadata": metadata,
                "device_used": device
            }
            
    except Exception as e:
        logger.error(f"Error processing document: {e}")
        return {
            "status": "error",
            "error": str(e)
        }

async def test_lightrag_server_integration():
    """Test the LightRAG server integration"""
    print("=== Testing LightRAG Server Integration ===")
    
    try:
        # Initialize client
        client = LightRAGServerClient()
        
        print("1. Checking server status...")
        status = await client.check_server_status()
        print(f"   Server status: {status}")
        
        if status.get("error"):
            print("   Server not accessible - check URL and API key")
            return
        
        print("\n2. Testing simple upload...")
        test_content = "This is a test document about Althen sensors for testing the LightRAG server integration."
        test_metadata = {
            "test": True,
            "timestamp": datetime.now().isoformat()
        }
        
        upload_result = await client.upload_document(test_content, test_metadata)
        print(f"   Upload result: {upload_result}")
        
        if not upload_result.get("error"):
            print("\n3. Testing query...")
            query_result = await client.query_server("What is this test about?")
            print(f"   Query result: {query_result}")
        
        print("\n4. Test completed!")
        
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_lightrag_server_integration())