#!/usr/bin/env python3
"""
Process pages with enhanced MinerU extraction and web content fallback
"""
import os
import sys
import asyncio
import glob
import tempfile
import requests
import traceback
from pathlib import Path
from bs4 import BeautifulSoup

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

async def process_page_with_fallback(page_id: int):
    """Process a page with MinerU extraction or web content fallback"""
    try:
        logger.info(f"Processing page {page_id} with enhanced extraction...")
        
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
        
        combined_content = ""
        all_images_uploaded = []
        
        if datasheets:
            # Process datasheets with MinerU
            logger.info("Processing with MinerU extraction...")
            all_content = []
            
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
                            
                            for image_file in image_files:
                                image_path = os.path.join(images_dir, image_file)
                                
                                with open(image_path, 'rb') as img_f:
                                    image_data = img_f.read()
                                
                                image_url = await upload_image_to_supabase(
                                    image_data,
                                    f"page_{page_id}_{image_file}",
                                    page_id,
                                    datasheet['id']
                                )
                                
                                if image_url:
                                    image_url_map[f"images/{image_file}"] = image_url
                                    all_images_uploaded.append(image_url)
                        
                        # Replace image paths with Supabase URLs
                        processed_content = content
                        for local_path, supabase_url in image_url_map.items():
                            processed_content = processed_content.replace(local_path, supabase_url)
                        
                        all_content.append(processed_content)
                        logger.info(f"Successfully processed datasheet with {len(image_url_map)} images")
                        
                finally:
                    if os.path.exists(pdf_path):
                        os.unlink(pdf_path)
            
            # Create combined document from datasheets
            combined_content = f"""# {page_data.get('category', 'Product')} - {page_data.get('subcategory', 'Technical Documentation')}

**URL:** {page_url}
**Business Area:** {page_data.get('business_area', 'sensors')}
**Page Type:** {page_data.get('page_type', 'product')}

---

{"".join(all_content)}

---
*Processed from {len(datasheets)} datasheet(s) with {len(all_images_uploaded)} images using enhanced MinerU extraction*
"""
        
        else:
            # Fallback to web content scraping
            logger.info("No datasheets found - processing web content only")
            
            try:
                logger.info(f"Scraping web content from: {page_url}")
                response = requests.get(page_url, timeout=30)
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.extract()
                
                # Get text content
                text = soup.get_text()
                
                # Clean up text
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                web_content = ' '.join(chunk for chunk in chunks if chunk)
                
                # Limit content length
                if len(web_content) > 5000:
                    web_content = web_content[:5000] + "..."
                
                logger.info(f"Extracted {len(web_content)} characters of web content")
                
                # Create document from web content
                combined_content = f"""# {page_data.get('category', 'Page')} - {page_data.get('subcategory', 'Web Content')}

**URL:** {page_url}
**Business Area:** {page_data.get('business_area', 'unknown')}
**Page Type:** {page_data.get('page_type', 'web')}

---

{web_content}

---
*Processed from web content only - no datasheets available*
"""
                
            except Exception as web_error:
                logger.error(f"Failed to process web content: {web_error}")
                return {"success": False, "error": f"No datasheets and web scraping failed: {web_error}"}
        
        logger.info(f"Created combined document: {len(combined_content)} characters")
        
        # Upload to Supabase storage
        doc_url = await upload_processed_document_to_supabase(
            combined_content,
            page_data,
            {
                "processing_method": "enhanced_extraction_with_fallback",
                "datasheets_processed": len(datasheets),
                "images_uploaded": len(all_images_uploaded),
                "content_length": len(combined_content)
            }
        )
        
        # Upload to LightRAG server via API
        try:
            lightrag_server_url = os.getenv("LIGHTRAG_SERVER_URL", "http://localhost:8020")
            lightrag_api_key = os.getenv("LIGHTRAG_API_KEY")
            
            headers = {'Content-Type': 'application/json'}
            if lightrag_api_key:
                headers['X-API-Key'] = lightrag_api_key
            
            payload = {
                "text": combined_content,
                "file_source": f"page_{page_id}_{page_data.get('category', 'content').lower().replace(' ', '_')}"
            }
            
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
            "doc_url": doc_url,
            "processing_method": "datasheets" if datasheets else "web_content"
        }
        
    except Exception as e:
        logger.error(f"Error processing page {page_id}: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python process_page_with_web_fallback.py <page_id>")
        sys.exit(1)
    
    page_id = int(sys.argv[1])
    result = asyncio.run(process_page_with_fallback(page_id))
    
    if result["success"]:
        print(f"""
🎉 SUCCESS!
Page ID: {result['page_id']}
Content Length: {result['content_length']:,} characters
Images Uploaded: {result['images_uploaded']}
Datasheets Processed: {result['datasheets_processed']}
Processing Method: {result['processing_method']}
Document URL: {result.get('doc_url', 'N/A')}
""")
    else:
        print(f"❌ FAILED: {result['error']}")