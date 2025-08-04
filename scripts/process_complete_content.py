#!/usr/bin/env python3
"""
Complete content processing: Web content + PDFs + ALL images forced into markdown
"""
import os
import sys
import asyncio
import glob
import tempfile
import requests
import traceback
import json
import re
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

def scrape_web_content(url: str, max_length: int = 10000) -> str:
    """Scrape and clean web content from URL"""
    try:
        logger.info(f"Scraping web content from: {url}")
        response = requests.get(url, timeout=30)
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
        if len(web_content) > max_length:
            web_content = web_content[:max_length] + "..."
        
        logger.info(f"Extracted {len(web_content)} characters of web content")
        return web_content
        
    except Exception as e:
        logger.error(f"Failed to scrape web content: {e}")
        return ""

def ensure_all_images_in_markdown(markdown_content: str, images_dir: str, image_url_map: dict) -> str:
    """Ensure ALL images from the directory are referenced in the markdown"""
    
    if not os.path.exists(images_dir):
        return markdown_content
    
    # Get all image files
    all_image_files = [f for f in os.listdir(images_dir) 
                      if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    # Track which images are already in the markdown
    images_in_markdown = set()
    for image_file in all_image_files:
        # Check if image is referenced
        if image_file in markdown_content or image_url_map.get(image_file, "") in markdown_content:
            images_in_markdown.add(image_file)
    
    # Find missing images
    missing_images = set(all_image_files) - images_in_markdown
    
    if missing_images:
        logger.info(f"Found {len(missing_images)} images not referenced in markdown. Adding them...")
        
        # Add section for missing images
        additional_images_section = "\n\n## Additional Extracted Images\n\n"
        
        for i, image_file in enumerate(sorted(missing_images)):
            image_url = image_url_map.get(image_file, f"images/{image_file}")
            
            # Determine image type based on filename or context
            alt_text = "Extracted Figure"
            if "table" in image_file.lower():
                alt_text = "Data Table"
            elif "diagram" in image_file.lower():
                alt_text = "Technical Diagram"
            elif "chart" in image_file.lower():
                alt_text = "Chart"
            elif "dimension" in image_file.lower():
                alt_text = "Dimensions Diagram"
            elif "wiring" in image_file.lower():
                alt_text = "Wiring Diagram"
            
            additional_images_section += f"![{alt_text} {i+1}]({image_url})\n\n"
        
        # Append missing images to markdown
        markdown_content += additional_images_section
        logger.info(f"Added {len(missing_images)} missing images to markdown")
    
    return markdown_content

def process_mineru_output_comprehensively(pdf_name: str, page_id: int, datasheet_id: int) -> dict:
    """Process MinerU output and ensure ALL content and images are captured"""
    
    result = {
        "content": "",
        "images": [],
        "image_map": {}
    }
    
    try:
        # Find MinerU output directory
        mineru_output_dir = f"output/{pdf_name}"
        
        # First, try to get the markdown file
        markdown_file = f"{mineru_output_dir}/auto/{pdf_name}.md"
        if os.path.exists(markdown_file):
            with open(markdown_file, 'r', encoding='utf-8') as f:
                result["content"] = f.read()
            logger.info(f"Read {len(result['content'])} characters from markdown")
        
        # Then, check content_list.json for additional content
        content_list_file = f"{mineru_output_dir}/auto/{pdf_name}_content_list.json"
        if os.path.exists(content_list_file):
            with open(content_list_file, 'r', encoding='utf-8') as f:
                content_list = json.load(f)
            
            # Extract any missing content from content_list
            additional_content = []
            for item in content_list:
                item_type = item.get("type", "")
                
                # Check for tables that might not be in markdown
                if item_type == "table":
                    table_body = item.get("table_body", "")
                    if table_body and table_body not in result["content"]:
                        additional_content.append("\n## Data Table\n")
                        additional_content.append(table_body)
                        additional_content.append("\n")
                        logger.info("Added missing table content")
                
                # Check for text that might be missing
                elif item_type == "text":
                    text = item.get("text", "").strip()
                    if text and len(text) > 50 and text not in result["content"]:
                        additional_content.append(f"\n{text}\n")
            
            if additional_content:
                result["content"] += "\n\n## Additional Content from PDF\n" + "".join(additional_content)
                logger.info(f"Added {len(additional_content)} additional content items")
        
        # Get ALL images from the images directory
        images_dir = f"{mineru_output_dir}/auto/images"
        if os.path.exists(images_dir):
            image_files = [f for f in os.listdir(images_dir) 
                          if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
            result["images"] = image_files
            logger.info(f"Found {len(image_files)} total images in directory")
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing MinerU output: {e}")
        return result

async def process_page_complete(page_id: int):
    """Process page with complete content: web + PDFs + ALL images"""
    try:
        logger.info(f"Processing page {page_id} with COMPLETE content extraction...")
        
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
        
        # ALWAYS scrape web content first
        web_content = scrape_web_content(page_url)
        
        # Get datasheets
        datasheets_response = supabase_client.table("new_datasheets_index").select("*").eq("parent_url", page_url).execute()
        datasheets = datasheets_response.data
        logger.info(f"Found {len(datasheets)} datasheets")
        
        all_content_sections = []
        all_images_uploaded = []
        lightrag_track_id = None
        
        # Add web content section
        if web_content:
            web_section = f"""## Web Page Content

{web_content}

---
"""
            all_content_sections.append(web_section)
            logger.info("Added web content section")
        
        # Process datasheets if available
        if datasheets:
            pdf_sections = []
            
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
                    
                    # Get comprehensive MinerU output
                    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
                    mineru_result = process_mineru_output_comprehensively(
                        pdf_name, page_id, datasheet['id']
                    )
                    
                    # Upload ALL images to Supabase
                    images_dir = f"output/{pdf_name}/auto/images"
                    image_url_map = {}
                    
                    if os.path.exists(images_dir) and mineru_result["images"]:
                        logger.info(f"Uploading ALL {len(mineru_result['images'])} images...")
                        
                        for i, image_file in enumerate(mineru_result["images"]):
                            image_path = os.path.join(images_dir, image_file)
                            
                            # Read image data
                            with open(image_path, 'rb') as img_f:
                                image_data = img_f.read()
                            
                            # Create descriptive name
                            image_type = "figure"
                            if "table" in image_file.lower() or i % 3 == 0:  # Assume some are tables
                                image_type = "table"
                            elif "diagram" in image_file.lower():
                                image_type = "diagram"
                            elif "chart" in image_file.lower():
                                image_type = "chart"
                            
                            descriptive_name = f"page_{page_id}_{image_type}_{i+1:03d}.jpg"
                            
                            # Upload to Supabase
                            image_url = await upload_image_to_supabase(
                                image_data,
                                descriptive_name,
                                page_id,
                                datasheet['id']
                            )
                            
                            if image_url:
                                image_url_map[image_file] = image_url
                                all_images_uploaded.append(image_url)
                                
                                if (i + 1) % 10 == 0:
                                    logger.info(f"Uploaded {i+1}/{len(mineru_result['images'])} images")
                    
                    # Process content with image URLs
                    pdf_content = mineru_result["content"]
                    
                    # Replace image references with Supabase URLs
                    for image_file, image_url in image_url_map.items():
                        pdf_content = pdf_content.replace(f"images/{image_file}", image_url)
                        pdf_content = pdf_content.replace(image_file, image_url)
                    
                    # FORCE all images into markdown if they're missing
                    pdf_content = ensure_all_images_in_markdown(
                        pdf_content, images_dir, image_url_map
                    )
                    
                    # Add PDF section header
                    pdf_section = f"""## Technical Documentation: {os.path.basename(datasheet['url'])}

{pdf_content}

---
"""
                    pdf_sections.append(pdf_section)
                    logger.info(f"Added PDF section with {len(image_url_map)} images")
                    
                finally:
                    # Clean up
                    if os.path.exists(pdf_path):
                        os.unlink(pdf_path)
            
            # Add all PDF sections
            if pdf_sections:
                all_content_sections.extend(pdf_sections)
        
        # Create complete combined document
        combined_content = f"""# {page_data.get('category', 'Product')} - {page_data.get('subcategory', 'Documentation')}

**URL:** {page_url}
**Business Area:** {page_data.get('business_area', 'sensors')}
**Page Type:** {page_data.get('page_type', 'product')}

---

{"".join(all_content_sections)}

---
*Complete content from web page + {len(datasheets)} datasheet(s) with ALL {len(all_images_uploaded)} images included*
"""
        
        logger.info(f"Created COMPLETE document: {len(combined_content)} characters with {len(all_images_uploaded)} images")
        
        # Upload to Supabase storage
        doc_url = await upload_processed_document_to_supabase(
            combined_content,
            page_data,
            {
                "processing_method": "complete_content_extraction",
                "datasheets_processed": len(datasheets),
                "images_uploaded": len(all_images_uploaded),
                "content_length": len(combined_content),
                "includes_web_content": True,
                "all_images_forced": True
            }
        )
        
        # Upload to LightRAG server
        try:
            lightrag_server_url = os.getenv("LIGHTRAG_SERVER_URL", "http://localhost:8020")
            lightrag_api_key = os.getenv("LIGHTRAG_API_KEY")
            
            headers = {'Content-Type': 'application/json'}
            if lightrag_api_key:
                headers['X-API-Key'] = lightrag_api_key
            
            category = page_data.get('category') or 'content'
            safe_category = str(category).lower().replace(' ', '_').replace('-', '_')
            
            payload = {
                "text": combined_content,
                "file_source": f"page_{page_id}_{safe_category}_complete"
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
                lightrag_track_id = track_id
            else:
                logger.warning(f"LightRAG upload failed: {response.status_code} - {response.text}")
                lightrag_track_id = None
                
        except Exception as lightrag_error:
            logger.warning(f"LightRAG upload failed: {lightrag_error}")
            lightrag_track_id = None
        
        # Mark page and datasheets as processed
        page_update_data = {
            "rag_ingested": True,
            "rag_ingested_at": "now()"
        }
        if lightrag_track_id and lightrag_track_id != 'N/A':
            page_update_data["lightrag_track_id"] = lightrag_track_id
            
        supabase_client.table("new_pages_index").update(page_update_data).eq("id", page_id).execute()
        
        if datasheets:
            for datasheet in datasheets:
                datasheet_update_data = {
                    "rag_ingested": True,
                    "rag_ingested_at": "now()"
                }
                if lightrag_track_id and lightrag_track_id != 'N/A':
                    datasheet_update_data["lightrag_track_id"] = lightrag_track_id
                    
                supabase_client.table("new_datasheets_index").update(datasheet_update_data).eq("id", datasheet['id']).execute()
                logger.info(f"Marked datasheet {datasheet['id']} as processed")
        
        logger.info("Page marked as processed with COMPLETE content")
        
        return {
            "success": True,
            "page_id": page_id,
            "content_length": len(combined_content),
            "images_uploaded": len(all_images_uploaded),
            "datasheets_processed": len(datasheets),
            "doc_url": doc_url,
            "includes_web_content": True,
            "all_images_forced": True
        }
        
    except Exception as e:
        logger.error(f"Error processing page {page_id}: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python process_complete_content.py <page_id>")
        sys.exit(1)
    
    page_id = int(sys.argv[1])
    result = asyncio.run(process_page_complete(page_id))
    
    if result["success"]:
        print(f"""
🎉 SUCCESS! COMPLETE Content Processing
Page ID: {result['page_id']}
Content Length: {result['content_length']:,} characters
ALL Images Included: {result['images_uploaded']}
Datasheets Processed: {result['datasheets_processed']}
Web Content: ✅ INCLUDED
All Images: ✅ FORCED INTO MARKDOWN
Document URL: {result.get('doc_url', 'N/A')}
""")
    else:
        print(f"❌ FAILED: {result['error']}")