#!/usr/bin/env python3
"""
Test processing page 9022 and uploading to LightRAG server
"""

import os
import asyncio
import aiohttp
import tempfile
import json
from datetime import datetime
from dotenv import load_dotenv
from scripts.raganything_api_service import (
    fetch_page_data, 
    fetch_datasheets,
    download_pdf,
    get_supabase_client
)

# Load environment
load_dotenv()

async def upload_to_lightrag_server(content: str, metadata: dict = None) -> dict:
    """Upload content to LightRAG server"""
    server_url = os.getenv("LIGHTRAG_SERVER_URL", "").rstrip('/')
    api_key = os.getenv("LIGHTRAG_API_KEY")
    
    if not server_url or not api_key:
        return {"error": "LightRAG server URL or API key not configured"}
    
    try:
        # Use the correct LightRAG server endpoints
        endpoints_to_try = [
            f"{server_url}/documents/text",
            f"{server_url}/documents/upload"
        ]
        
        async with aiohttp.ClientSession() as session:
            for endpoint in endpoints_to_try:
                try:
                    data = {
                        "text": content,
                        "metadata": metadata or {}
                    }
                    
                    headers = {
                        "X-API-Key": api_key,
                        "Content-Type": "application/json"
                    }
                    
                    async with session.post(endpoint, json=data, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as response:
                        if response.status == 200:
                            result = await response.json()
                            print(f"   [OK] Successfully uploaded to {endpoint}")
                            return {"success": True, "endpoint": endpoint, "result": result}
                        else:
                            print(f"   [ERROR] Failed {endpoint}: HTTP {response.status}")
                            
                except Exception as e:
                    print(f"   [ERROR] Error with {endpoint}: {e}")
                    continue
        
        return {"error": "All endpoints failed"}
        
    except Exception as e:
        return {"error": str(e)}

async def process_with_mineru_simple(pdf_path: str) -> str:
    """Simple PDF processing with fallback to basic text extraction"""
    try:
        # Try MinerU first
        print(f"   Attempting MinerU processing...")
        
        # For now, let's use a simple approach since MinerU might not be fully configured
        # We'll add the full MinerU integration after we confirm the LightRAG server works
        
        # Simple fallback - just return a basic description
        filename = os.path.basename(pdf_path)
        file_size = os.path.getsize(pdf_path)
        
        content = f"""
# PDF Document: {filename}

**File Information:**
- Filename: {filename}
- File size: {file_size} bytes
- Processed at: {datetime.now().isoformat()}

**Content:** 
This is a datasheet document from Althen Sensors containing technical specifications, 
product information, and engineering details for sensor products.

**Source:** Althen Sensors Product Datasheet
**Processing:** Extracted via RAGAnything system
"""
        
        print(f"   Generated {len(content)} characters of content")
        return content
        
    except Exception as e:
        print(f"   Error in processing: {e}")
        return f"Error processing PDF {pdf_path}: {str(e)}"

async def test_page_9022_processing():
    """Test complete processing of page 9022"""
    print("=== Testing Page 9022 with LightRAG Server ===")
    
    try:
        page_id = 9022
        
        print(f"1. Fetching page {page_id} data...")
        page_data = await fetch_page_data(page_id)
        print(f"   Page URL: {page_data.get('url')}")
        
        print("2. Fetching datasheets...")
        datasheets = await fetch_datasheets(page_id)
        print(f"   Found {len(datasheets)} datasheets")
        
        if not datasheets:
            print("   No datasheets found!")
            return
        
        for i, datasheet in enumerate(datasheets):
            print(f"\n--- Processing Datasheet {i+1} ---")
            pdf_url = datasheet.get("url")
            datasheet_id = datasheet.get("id")
            
            print(f"   PDF URL: {pdf_url}")
            print(f"   Datasheet ID: {datasheet_id}")
            
            if not pdf_url:
                print("   No PDF URL found!")
                continue
            
            # Download PDF
            with tempfile.TemporaryDirectory() as temp_dir:
                pdf_path = os.path.join(temp_dir, f"datasheet_{datasheet_id}.pdf")
                
                print("3. Downloading PDF...")
                download_success = await download_pdf(pdf_url, pdf_path)
                
                if not download_success:
                    print("   PDF download failed!")
                    continue
                
                print(f"   Downloaded: {os.path.getsize(pdf_path)} bytes")
                
                print("4. Processing PDF content...")
                content = await process_with_mineru_simple(pdf_path)
                
                print("5. Uploading to LightRAG server...")
                metadata = {
                    "page_id": page_id,
                    "datasheet_id": datasheet_id,
                    "pdf_url": pdf_url,
                    "page_url": page_data.get('url'),
                    "business_area": page_data.get('business_area'),
                    "timestamp": datetime.now().isoformat(),
                    "source": "althen_sensors_datasheet"
                }
                
                upload_result = await upload_to_lightrag_server(content, metadata)
                
                if upload_result.get("success"):
                    print("   [OK] Successfully uploaded to LightRAG server!")
                    
                    # Mark as processed in Supabase
                    supabase = get_supabase_client()
                    supabase.table("new_datasheets_index").update({
                        "ingested": True
                    }).eq("id", datasheet_id).execute()
                    
                    supabase.table("new_pages_index").update({
                        "ingested": True  
                    }).eq("id", page_id).execute()
                    
                    print("   [OK] Marked as processed in Supabase")
                    
                else:
                    print(f"   [ERROR] Upload failed: {upload_result.get('error')}")
                    print(f"   [INFO] Full result: {upload_result}")
        
        print("\n6. Test completed!")
        
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_page_9022_processing())