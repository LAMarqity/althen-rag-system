#!/usr/bin/env python3
"""
Enhanced processing that improves empty alt text in existing images and adds missing ones
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

def generate_smart_description(img_info: dict, surrounding_text: str = "") -> str:
    """Generate intelligent image description"""
    
    caption = img_info.get("caption", "").strip()
    footnote = img_info.get("footnote", "").strip()
    img_type = img_info.get("type", "image")
    
    # If we have a meaningful caption, use it
    if caption and len(caption) > 3:
        if img_type == "table":
            return f"Table: {caption}"
        else:
            return f"Figure: {caption}"
    
    # Analyze context for technical keywords
    all_text = f"{caption} {footnote} {surrounding_text}".lower()
    
    technical_patterns = {
        "dimensions": ["dimension", "mm", "inch", "size", "diameter", "length", "width", "height"],
        "wiring": ["wiring", "wire", "cable", "connection", "pin", "connector", "electrical"],
        "mounting": ["mount", "installation", "bracket", "hole", "assembly"],
        "performance": ["performance", "curve", "graph", "chart", "specification"],
        "calibration": ["calibration", "accuracy", "linearity", "error"]
    }
    
    detected_type = None
    for pattern_type, keywords in technical_patterns.items():
        if any(keyword in all_text for keyword in keywords):
            detected_type = pattern_type
            break
    
    # Generate description
    if img_type == "table":
        if detected_type == "dimensions":
            return "Dimensional Specifications Table"
        elif detected_type == "performance":
            return "Performance Characteristics Table"
        elif detected_type == "wiring":
            return "Electrical Connection Table"
        else:
            return "Technical Specifications Table"
    else:
        if detected_type == "dimensions":
            return "Dimensional Drawing"
        elif detected_type == "wiring":
            return "Wiring Diagram"
        elif detected_type == "mounting":
            return "Mounting Configuration"
        elif detected_type == "performance":
            return "Performance Chart"
        else:
            return "Technical Figure"

def extract_images_with_context(content_list_file: str) -> dict:
    """Extract all images with context, indexed by filename"""
    images_map = {}
    try:
        with open(content_list_file, 'r', encoding='utf-8') as f:
            content_list = json.load(f)
        
        # Build context by looking at surrounding text
        for i, item in enumerate(content_list):
            item_type = item.get("type", "")
            
            # Get surrounding text context
            context_text = ""
            for j in range(max(0, i-2), min(len(content_list), i+3)):
                if j != i and content_list[j].get("type") == "text":
                    text = content_list[j].get("text", "").strip()
                    if text:
                        context_text += f" {text}"
            
            if item_type in ["image", "table"]:
                img_path = item.get("img_path", "")
                if img_path:
                    filename = os.path.basename(img_path)
                    images_map[filename] = {
                        "filename": filename,
                        "caption": " ".join(item.get("image_caption" if item_type == "image" else "table_caption", [])).strip(),
                        "footnote": " ".join(item.get("image_footnote", [])).strip(),
                        "type": item_type,
                        "context": context_text.strip()
                    }
    
    except Exception as e:
        logger.error(f"Error extracting images from content_list: {e}")
    
    return images_map

def enhance_existing_alt_text(markdown_content: str, image_url_map: dict, images_context_map: dict) -> str:
    """Enhance existing images by improving empty alt text, add missing images separately"""
    
    # First, replace local paths with Supabase URLs
    for local_filename, supabase_url in image_url_map.items():
        patterns = [
            f"images/{local_filename}",
            f"./images/{local_filename}",
            f"auto/images/{local_filename}"
        ]
        for pattern in patterns:
            markdown_content = markdown_content.replace(f"]({pattern})", f"]({supabase_url})")
    
    # Track which images are used in the markdown
    used_images = set()
    
    # Find and enhance images with empty or minimal alt text
    def enhance_alt_text(match):
        alt_text = match.group(1)
        url = match.group(2)
        
        # Extract filename from URL
        filename_match = re.search(r'([^/]+\.(?:jpg|jpeg|png))', url, re.IGNORECASE)
        if not filename_match:
            return match.group(0)  # Return original if can't extract filename
        
        supabase_filename = filename_match.group(1)
        
        # Find the original filename that maps to this Supabase URL
        original_filename = None
        for orig_name, supabase_url in image_url_map.items():
            if supabase_url == url:
                original_filename = orig_name
                break
        
        if not original_filename:
            return match.group(0)  # Return original if can't find mapping
        
        used_images.add(original_filename)
        
        # If alt text is empty or very short, enhance it
        if not alt_text.strip() or len(alt_text.strip()) < 3:
            if original_filename in images_context_map:
                img_info = images_context_map[original_filename]
                smart_alt = generate_smart_description(img_info, img_info["context"])
                logger.info(f"Enhanced empty alt text for {original_filename}: '{smart_alt}'")
                return f"![{smart_alt}]({url})"
        
        # Return original if alt text is already good
        return match.group(0)
    
    # Pattern to match all images: ![alt text](url)
    image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    enhanced_markdown = re.sub(image_pattern, enhance_alt_text, markdown_content)
    
    # Find images that weren't used in the markdown and add them
    unused_images = []
    for filename in image_url_map.keys():
        if filename not in used_images:
            unused_images.append(filename)
    
    if unused_images:
        logger.info(f"Found {len(unused_images)} unused images to add: {unused_images}")
        enhanced_markdown += "\n\n## Additional Technical Documentation\n\n"
        
        for filename in unused_images:
            if filename in image_url_map and filename in images_context_map:
                url = image_url_map[filename]
                img_info = images_context_map[filename]
                smart_description = generate_smart_description(img_info, img_info["context"])
                
                enhanced_markdown += f"![{smart_description}]({url})\n"
                
                if img_info['caption']:
                    enhanced_markdown += f"*Caption: {img_info['caption']}*\n"
                if img_info['footnote']:
                    enhanced_markdown += f"*Note: {img_info['footnote']}*\n"
                
                enhanced_markdown += "\n"
    
    return enhanced_markdown

async def process_page_enhance_alt_text(page_id: int):
    """Process page by enhancing alt text without duplicating images"""
    try:
        logger.info(f"Processing page {page_id} by ENHANCING alt text without duplication...")
        
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
            # Process datasheets with enhanced alt text
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
                            descriptive_name = f"page_{page_id}_img_{i+1:03d}.jpg"
                            
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
                                    logger.info(f"Uploaded {i+1}/{len(image_files)} images")
                        
                        logger.info(f"Successfully uploaded {len(image_url_map)} images")
                    
                    # Get context for all images
                    content_list_file = f"{mineru_output_dir}/auto/{pdf_name}_content_list.json"
                    images_context_map = extract_images_with_context(content_list_file)
                    
                    # Read original markdown and enhance alt text
                    markdown_file = f"{mineru_output_dir}/auto/{pdf_name}.md"
                    if os.path.exists(markdown_file):
                        with open(markdown_file, 'r', encoding='utf-8') as f:
                            original_markdown = f.read()
                        
                        # Enhance alt text without duplicating images
                        pdf_content = enhance_existing_alt_text(original_markdown, image_url_map, images_context_map)
                        logger.info("Enhanced alt text for existing images")
                    else:
                        pdf_content = "No markdown content found"
                    
                    # Create section for this datasheet
                    datasheet_section = f"""## Technical Documentation: {os.path.basename(datasheet['url'])}

{pdf_content}

---
"""
                    all_content_sections.append(datasheet_section)
                    logger.info(f"Added datasheet section with enhanced alt text")
                    
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
*Complete content: Web page + {len(datasheets)} datasheet(s) with {len(all_images_uploaded)} images (enhanced alt text)*
"""
        
        logger.info(f"Created document with ENHANCED alt text: {len(combined_content)} characters, {len(all_images_uploaded)} images")
        
        # Upload to Supabase storage
        doc_url = await upload_processed_document_to_supabase(
            combined_content,
            page_data,
            {
                "processing_method": "enhanced_alt_text_no_duplication",
                "datasheets_processed": len(datasheets),
                "images_uploaded": len(all_images_uploaded),
                "content_length": len(combined_content),
                "includes_web_content": True,
                "enhanced_alt_text": True
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
                "file_source": f"page_{page_id}_{safe_category}_enhanced_alt"
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
        
        logger.info("ENHANCED ALT TEXT processing complete!")
        
        return {
            "success": True,
            "page_id": page_id,
            "content_length": len(combined_content),
            "images_uploaded": len(all_images_uploaded),
            "datasheets_processed": len(datasheets),
            "doc_url": doc_url,
            "includes_web_content": bool(web_content),
            "enhanced_alt_text": True
        }
        
    except Exception as e:
        logger.error(f"Error processing page {page_id}: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python process_enhance_alt_text.py <page_id>")
        sys.exit(1)
    
    page_id = int(sys.argv[1])
    result = asyncio.run(process_page_enhance_alt_text(page_id))
    
    if result["success"]:
        print(f"""
SUCCESS! ENHANCED ALT TEXT WITHOUT DUPLICATION
Page ID: {result['page_id']}
Content Length: {result['content_length']:,} characters
Images Uploaded: {result['images_uploaded']}
Datasheets Processed: {result['datasheets_processed']}
Web Content Included: {'YES' if result.get('includes_web_content') else 'NO'}
Enhanced Alt Text: {'YES' if result.get('enhanced_alt_text') else 'NO'}
Document URL: {result.get('doc_url', 'N/A')}
""")
    else:
        print(f"FAILED: {result['error']}")