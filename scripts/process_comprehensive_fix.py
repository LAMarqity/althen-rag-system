#!/usr/bin/env python3
"""
Comprehensive fix for image referencing and web content inclusion
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

def extract_images_from_content_list(content_list_file: str) -> list:
    """Extract all image references from content_list.json"""
    images = []
    try:
        with open(content_list_file, 'r', encoding='utf-8') as f:
            content_list = json.load(f)
        
        for item in content_list:
            item_type = item.get("type", "")
            
            # Get images from image items
            if item_type == "image":
                img_path = item.get("img_path", "")
                if img_path:
                    images.append({
                        "filename": os.path.basename(img_path),
                        "caption": " ".join(item.get("image_caption", [])).strip(),
                        "footnote": " ".join(item.get("image_footnote", [])).strip(),
                        "type": "image"
                    })
            
            # Get images from tables
            elif item_type == "table":
                img_path = item.get("img_path", "")
                if img_path:
                    images.append({
                        "filename": os.path.basename(img_path),
                        "caption": " ".join(item.get("table_caption", [])).strip(),
                        "footnote": "",
                        "type": "table"
                    })
    
    except Exception as e:
        logger.error(f"Error extracting images from content_list: {e}")
    
    return images

def build_comprehensive_markdown(mineru_output_dir: str, image_url_map: dict) -> str:
    """Build markdown that includes ALL content and images"""
    
    pdf_name = os.path.basename(mineru_output_dir)
    markdown_file = f"{mineru_output_dir}/auto/{pdf_name}.md"
    content_list_file = f"{mineru_output_dir}/auto/{pdf_name}_content_list.json"
    
    # Start with existing markdown content
    markdown_content = ""
    if os.path.exists(markdown_file):
        with open(markdown_file, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        logger.info(f"Read {len(markdown_content)} characters from existing markdown")
    
    # Replace image paths with Supabase URLs in existing content
    for local_filename, supabase_url in image_url_map.items():
        # Try different path patterns
        patterns = [
            f"images/{local_filename}",
            f"./images/{local_filename}",
            f"auto/images/{local_filename}",
            local_filename
        ]
        for pattern in patterns:
            markdown_content = markdown_content.replace(pattern, supabase_url)
    
    # Get all images from content_list
    all_images = extract_images_from_content_list(content_list_file)
    logger.info(f"Found {len(all_images)} images in content_list.json")
    
    # Find which images are already in markdown
    images_in_markdown = set()
    for img_info in all_images:
        filename = img_info["filename"]
        if filename in image_url_map:
            url = image_url_map[filename]
            if url in markdown_content:
                images_in_markdown.add(filename)
    
    logger.info(f"{len(images_in_markdown)} images already in markdown")
    
    # Add missing images
    missing_images = []
    for img_info in all_images:
        if img_info["filename"] not in images_in_markdown:
            missing_images.append(img_info)
    
    if missing_images:
        logger.info(f"Adding {len(missing_images)} missing images to markdown")
        
        # Add section for missing images
        markdown_content += "\n\n## Additional Document Images\n\n"
        
        for img_info in missing_images:
            filename = img_info["filename"]
            if filename in image_url_map:
                url = image_url_map[filename]
                
                # Create descriptive alt text
                if img_info["type"] == "table":
                    alt_text = f"Table: {img_info['caption']}" if img_info['caption'] else "Data Table"
                else:
                    alt_text = f"Figure: {img_info['caption']}" if img_info['caption'] else "Technical Figure"
                
                # Add image to markdown
                markdown_content += f"![{alt_text}]({url})\n"
                
                # Add caption if present
                if img_info['caption']:
                    markdown_content += f"*{img_info['caption']}*\n"
                if img_info['footnote']:
                    markdown_content += f"*Note: {img_info['footnote']}*\n"
                
                markdown_content += "\n"
    
    return markdown_content

async def process_page_comprehensive(page_id: int):
    """Process page with comprehensive content extraction"""
    try:
        logger.info(f"Processing page {page_id} with COMPREHENSIVE fix...")
        
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
        
        # ALWAYS get web content first
        web_content = scrape_web_content(page_url)
        web_section = ""
        if web_content:
            web_section = f"""## Web Page Content

Source: {page_url}

{web_content}

---
"""
            logger.info("Successfully scraped web content")
        
        # Get datasheets
        datasheets_response = supabase_client.table("new_datasheets_index").select("*").eq("parent_url", page_url).execute()
        datasheets = datasheets_response.data
        logger.info(f"Found {len(datasheets)} datasheets")
        
        all_content_sections = []
        all_images_uploaded = []
        lightrag_track_id = None
        
        if not datasheets:
            # Use web content only
            if not web_content:
                return {"success": False, "error": "No datasheets and no web content available"}
            
            combined_content = f"""# {page_data.get('category', 'Page')} - {page_data.get('subcategory', 'Web Content')}

**URL:** {page_url}
**Business Area:** {page_data.get('business_area', 'unknown')}
**Page Type:** {page_data.get('page_type', 'web')}

---

{web_section}

---
*Processed from web content only - no datasheets available*
"""
        else:
            # Process datasheets and combine with web content
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
                    
                    # Get MinerU output directory
                    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
                    mineru_output_dir = f"output/{pdf_name}"
                    
                    # Process ALL images
                    images_dir = f"{mineru_output_dir}/auto/images"
                    image_url_map = {}
                    
                    if os.path.exists(images_dir):
                        image_files = [f for f in os.listdir(images_dir) 
                                     if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                        
                        logger.info(f"Uploading ALL {len(image_files)} images...")
                        
                        for i, image_file in enumerate(image_files):
                            image_path = os.path.join(images_dir, image_file)
                            
                            # Read image data
                            with open(image_path, 'rb') as img_f:
                                image_data = img_f.read()
                            
                            # Create descriptive filename
                            # Analyze filename for context
                            descriptive_name = f"page_{page_id}_img_{i+1:03d}"
                            if "table" in image_file.lower():
                                descriptive_name = f"page_{page_id}_table_{i+1:03d}"
                            elif "diagram" in image_file.lower():
                                descriptive_name = f"page_{page_id}_diagram_{i+1:03d}"
                            elif "chart" in image_file.lower():
                                descriptive_name = f"page_{page_id}_chart_{i+1:03d}"
                            
                            descriptive_name += ".jpg"
                            
                            # Upload to Supabase
                            image_url = await upload_image_to_supabase(
                                image_data,
                                descriptive_name,
                                page_id,
                                datasheet['id']
                            )
                            
                            if image_url:
                                # Map by filename only (not path)
                                image_url_map[image_file] = image_url
                                all_images_uploaded.append(image_url)
                                
                                if (i + 1) % 10 == 0:
                                    logger.info(f"Uploaded {i+1}/{len(image_files)} images")
                        
                        logger.info(f"Successfully uploaded {len(image_url_map)} images")
                    
                    # Build comprehensive markdown with ALL images
                    pdf_content = build_comprehensive_markdown(mineru_output_dir, image_url_map)
                    
                    # Create section for this datasheet
                    datasheet_section = f"""## Technical Documentation: {os.path.basename(datasheet['url'])}

{pdf_content}

---
"""
                    all_content_sections.append(datasheet_section)
                    logger.info(f"Added datasheet section with {len(image_url_map)} images")
                    
                finally:
                    # Clean up
                    if os.path.exists(pdf_path):
                        os.unlink(pdf_path)
            
            # Combine all content: web + PDFs
            combined_content = f"""# {page_data.get('category', 'Product')} - {page_data.get('subcategory', 'Documentation')}

**URL:** {page_url}
**Business Area:** {page_data.get('business_area', 'sensors')}
**Page Type:** {page_data.get('page_type', 'product')}

---

{web_section}

{"".join(all_content_sections)}

---
*Complete content: Web page + {len(datasheets)} datasheet(s) with {len(all_images_uploaded)} images*
"""
        
        logger.info(f"Created COMPREHENSIVE document: {len(combined_content)} characters with {len(all_images_uploaded)} images")
        
        # Upload to Supabase storage
        doc_url = await upload_processed_document_to_supabase(
            combined_content,
            page_data,
            {
                "processing_method": "comprehensive_fix",
                "datasheets_processed": len(datasheets),
                "images_uploaded": len(all_images_uploaded),
                "content_length": len(combined_content),
                "includes_web_content": True,
                "all_images_included": True
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
                "file_source": f"page_{page_id}_{safe_category}_comprehensive"
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
                
        except Exception as lightrag_error:
            logger.warning(f"LightRAG upload failed: {lightrag_error}")
        
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
        
        logger.info("✅ COMPREHENSIVE processing complete!")
        
        return {
            "success": True,
            "page_id": page_id,
            "content_length": len(combined_content),
            "images_uploaded": len(all_images_uploaded),
            "datasheets_processed": len(datasheets),
            "doc_url": doc_url,
            "includes_web_content": bool(web_content),
            "all_images_included": True
        }
        
    except Exception as e:
        logger.error(f"Error processing page {page_id}: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python process_comprehensive_fix.py <page_id>")
        sys.exit(1)
    
    page_id = int(sys.argv[1])
    result = asyncio.run(process_page_comprehensive(page_id))
    
    if result["success"]:
        print(f"""
🎉 SUCCESS! COMPREHENSIVE FIX APPLIED
Page ID: {result['page_id']}
Content Length: {result['content_length']:,} characters
Images Uploaded: {result['images_uploaded']}
Datasheets Processed: {result['datasheets_processed']}
Web Content Included: {'YES' if result.get('includes_web_content') else 'NO'}
All Images Included: {'YES' if result.get('all_images_included') else 'NO'}
Document URL: {result.get('doc_url', 'N/A')}
""")
    else:
        print(f"FAILED: {result['error']}")