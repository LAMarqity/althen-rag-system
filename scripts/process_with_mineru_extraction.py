#!/usr/bin/env python3
"""
Production script to process pages with enhanced MinerU content extraction
"""
import os
import sys
import asyncio
import glob
import tempfile
import requests
import traceback
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.raganything_api_service import (
    get_supabase_client,
    logger,
    initialize_rag,
    upload_image_to_supabase,
    upload_processed_document_to_supabase
)

async def process_page_with_mineru(page_id: int):
    """Process a page with enhanced MinerU content extraction and upload to Supabase + LightRAG"""
    try:
        logger.info(f"Processing page {page_id} with enhanced MinerU extraction...")
        
        # Initialize
        supabase_client = get_supabase_client()
        await initialize_rag()
        
        from scripts.raganything_api_service import rag_instance
        if rag_instance is None:
            logger.error("RAG instance is None")
            return {"success": False, "error": "RAG initialization failed"}
        
        # Get page data
        page_response = supabase_client.table("new_pages_index").select("*").eq("id", page_id).execute()
        if not page_response.data:
            logger.error(f"Page {page_id} not found")
            return {"success": False, "error": "Page not found"}
            
        page_data = page_response.data[0]
        page_url = page_data['url']
        logger.info(f"Processing page: {page_url}")
        
        # Get datasheets
        datasheets_response = supabase_client.table("new_datasheets_index").select("*").eq("parent_url", page_url).execute()
        datasheets = datasheets_response.data
        logger.info(f"Found {len(datasheets)} datasheets")
        
        if not datasheets:
            logger.error("No datasheets found")
            return {"success": False, "error": "No datasheets found"}
        
        # Process each datasheet
        all_content = []
        all_images_uploaded = []
        
        for datasheet in datasheets:
            logger.info(f"Processing datasheet: {datasheet['url']}")
            
            # Download PDF
            response = requests.get(datasheet['url'])
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                tmp_file.write(response.content)
                pdf_path = tmp_file.name
            
            try:
                # Process with RAGAnything
                await rag_instance.process_document_complete(
                    pdf_path,
                    doc_id=f"page_{page_id}_datasheet_{datasheet['id']}"
                )
                
                # Extract MinerU content
                pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
                markdown_file = f"output/{pdf_name}/auto/{pdf_name}.md"
                
                if os.path.exists(markdown_file):
                    # Read the rich markdown content
                    with open(markdown_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    logger.info(f"Extracted {len(content)} characters of content")
                    
                    # Process images
                    images_dir = os.path.join(os.path.dirname(markdown_file), 'images')
                    image_url_map = {}
                    
                    if os.path.exists(images_dir):
                        image_files = [f for f in os.listdir(images_dir) 
                                     if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                        
                        logger.info(f"Uploading {len(image_files)} images...")
                        
                        for i, image_file in enumerate(image_files):
                            image_path = os.path.join(images_dir, image_file)
                            
                            # Read image data
                            with open(image_path, 'rb') as img_f:
                                image_data = img_f.read()
                            
                            # Upload to Supabase
                            image_url = await upload_image_to_supabase(
                                image_data,
                                f"page_{page_id}_{image_file}",
                                page_id,
                                datasheet['id']
                            )
                            
                            if image_url:
                                # Map local path to Supabase URL
                                image_url_map[f"images/{image_file}"] = image_url
                                all_images_uploaded.append(image_url)
                                
                                if i % 10 == 0:
                                    logger.info(f"Uploaded {i+1}/{len(image_files)} images")
                    
                    # Replace image paths in markdown with Supabase URLs
                    processed_content = content
                    for local_path, supabase_url in image_url_map.items():
                        processed_content = processed_content.replace(local_path, supabase_url)
                    
                    all_content.append(processed_content)
                    logger.info(f"Successfully processed datasheet with {len(image_url_map)} images")
                    
                else:
                    logger.warning(f"No MinerU output found for {pdf_name}")
                    
            finally:
                # Clean up
                if os.path.exists(pdf_path):
                    os.unlink(pdf_path)
        
        if not all_content:
            return {"success": False, "error": "No content was processed"}
        
        # Create combined document
        combined_content = f"""# {page_data.get('category', 'Product')} - {page_data.get('subcategory', 'Technical Documentation')}

**URL:** {page_url}
**Business Area:** {page_data.get('business_area', 'sensors')}
**Page Type:** {page_data.get('page_type', 'product')}

---

{"".join(all_content)}

---
*Processed from {len(datasheets)} datasheet(s) with {len(all_images_uploaded)} images using enhanced MinerU extraction*
"""
        
        logger.info(f"Created combined document: {len(combined_content)} characters")
        
        # Upload to Supabase storage
        doc_url = await upload_processed_document_to_supabase(
            combined_content,
            page_data,
            {
                "processing_method": "enhanced_mineru_extraction",
                "datasheets_processed": len(datasheets),
                "images_uploaded": len(all_images_uploaded),
                "content_length": len(combined_content)
            }
        )
        
        # Upload to LightRAG server via API
        try:
            # Get LightRAG server URL from environment
            lightrag_server_url = os.getenv("LIGHTRAG_SERVER_URL", "http://localhost:8020")
            lightrag_api_key = os.getenv("LIGHTRAG_API_KEY")
            
            # Prepare headers
            headers = {'Content-Type': 'application/json'}
            if lightrag_api_key:
                headers['X-API-Key'] = lightrag_api_key
            
            # Prepare payload for /documents/text API
            payload = {
                "text": combined_content,
                "file_source": f"page_{page_id}_crh03_series_gyroscope"
            }
            
            # Upload to LightRAG via API
            response = requests.post(
                f"{lightrag_server_url}/documents/text",
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Successfully uploaded to LightRAG server: {result.get('message', 'Success')}")
                track_id = result.get('track_id', 'N/A')
                logger.info(f"LightRAG track ID: {track_id}")
            else:
                logger.warning(f"LightRAG upload failed: {response.status_code} - {response.text}")
                
        except Exception as lightrag_error:
            logger.warning(f"LightRAG upload failed: {lightrag_error}")
        
        # Mark as processed
        supabase_client.table("new_pages_index").update({
            "rag_ingested": True,
            "rag_ingested_at": "now()"
        }).eq("id", page_id).execute()
        
        logger.info("Page marked as processed")
        
        return {
            "success": True,
            "page_id": page_id,
            "content_length": len(combined_content),
            "images_uploaded": len(all_images_uploaded),
            "datasheets_processed": len(datasheets),
            "doc_url": doc_url
        }
        
    except Exception as e:
        logger.error(f"Error processing page {page_id}: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python process_with_mineru_extraction.py <page_id>")
        sys.exit(1)
    
    page_id = int(sys.argv[1])
    result = asyncio.run(process_page_with_mineru(page_id))
    
    if result["success"]:
        print(f"""
🎉 SUCCESS!
Page ID: {result['page_id']}
Content Length: {result['content_length']:,} characters
Images Uploaded: {result['images_uploaded']}
Datasheets Processed: {result['datasheets_processed']}
Document URL: {result.get('doc_url', 'N/A')}
""")
    else:
        print(f"❌ FAILED: {result['error']}")