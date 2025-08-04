#!/usr/bin/env python3
"""
Enhanced processing that preserves existing image references and adds smart descriptions only to missing images
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

def generate_intelligent_description(img_info: dict, surrounding_text: str = "") -> str:
    """Generate intelligent image description based on MinerU data and context"""
    
    caption = img_info.get("caption", "").strip()
    footnote = img_info.get("footnote", "").strip()
    img_type = img_info.get("type", "image")
    filename = img_info.get("filename", "")
    
    # Combine all available text
    all_text = f"{caption} {footnote} {surrounding_text}".lower().strip()
    
    # If we have a meaningful caption, use it
    if caption and len(caption) > 3:
        if img_type == "table":
            return f"Table: {caption}"
        else:
            return f"Figure: {caption}"
    
    # Analyze filename and surrounding text for clues
    technical_keywords = {
        "dimensions": ["dimension", "mm", "inch", "size", "diameter", "length", "width", "height", "measure"],
        "wiring": ["wiring", "wire", "cable", "connection", "pin", "connector", "electrical", "circuit"],
        "performance": ["performance", "curve", "graph", "chart", "data", "specification", "specs"],
        "mounting": ["mount", "installation", "bracket", "hole", "assembly", "fixing"],
        "diagram": ["diagram", "schematic", "drawing", "layout", "plan", "structure"],
        "sensor": ["sensor", "transducer", "probe", "detector", "element"],
        "output": ["output", "signal", "voltage", "current", "response"],
        "calibration": ["calibration", "accuracy", "linearity", "error", "tolerance"],
        "temperature": ["temperature", "thermal", "heat", "temp", "celsius", "fahrenheit"],
        "pressure": ["pressure", "psi", "bar", "pascal", "force", "load"],
        "product": ["product", "model", "series", "photo", "image", "appearance"]
    }
    
    # Check for specific technical content
    detected_categories = []
    for category, keywords in technical_keywords.items():
        if any(keyword in all_text for keyword in keywords):
            detected_categories.append(category)
    
    # Generate description based on detected content
    if "table" in img_type.lower():
        if "dimensions" in detected_categories:
            return "Dimensional Specifications Table"
        elif "performance" in detected_categories:
            return "Performance Characteristics Table"
        elif "wiring" in detected_categories or "electrical" in all_text:
            return "Electrical Connection Table"
        elif "calibration" in detected_categories:
            return "Calibration Data Table"
        else:
            return "Technical Specifications Table"
    
    else:  # Regular image
        if "dimensions" in detected_categories:
            return "Dimensional Drawing"
        elif "wiring" in detected_categories:
            return "Wiring Diagram"
        elif "mounting" in detected_categories:
            return "Mounting Configuration"
        elif "performance" in detected_categories:
            return "Performance Chart"
        elif "diagram" in detected_categories:
            return "Technical Schematic"
        elif "product" in detected_categories:
            return "Product Photo"
        elif "sensor" in detected_categories:
            return "Sensor Configuration"
        elif "output" in detected_categories:
            return "Output Signal Diagram"
        elif "calibration" in detected_categories:
            return "Calibration Chart"
        elif "temperature" in detected_categories:
            return "Temperature Characteristics"
        elif "pressure" in detected_categories:
            return "Pressure Response"
        else:
            return "Technical Figure"

def extract_images_with_context(content_list_file: str) -> list:
    """Extract all images with their context from content_list.json"""
    images = []
    try:
        with open(content_list_file, 'r', encoding='utf-8') as f:
            content_list = json.load(f)
        
        # Build context by looking at surrounding text
        for i, item in enumerate(content_list):
            item_type = item.get("type", "")
            
            # Get surrounding text context (items before and after)
            context_text = ""
            for j in range(max(0, i-2), min(len(content_list), i+3)):
                if j != i and content_list[j].get("type") == "text":
                    text = content_list[j].get("text", "").strip()
                    if text:
                        context_text += f" {text}"
            
            if item_type == "image":
                img_path = item.get("img_path", "")
                if img_path:
                    images.append({
                        "filename": os.path.basename(img_path),
                        "caption": " ".join(item.get("image_caption", [])).strip(),
                        "footnote": " ".join(item.get("image_footnote", [])).strip(),
                        "type": "image",
                        "context": context_text.strip(),
                        "page_idx": item.get("page_idx", 0)
                    })
            
            elif item_type == "table":
                img_path = item.get("img_path", "")
                if img_path:
                    images.append({
                        "filename": os.path.basename(img_path),
                        "caption": " ".join(item.get("table_caption", [])).strip(),
                        "footnote": "",
                        "type": "table",
                        "context": context_text.strip(),
                        "page_idx": item.get("page_idx", 0)
                    })
    
    except Exception as e:
        logger.error(f"Error extracting images from content_list: {e}")
    
    return images

def preserve_and_enhance_markdown(mineru_output_dir: str, image_url_map: dict) -> str:
    """Preserve existing markdown and only add missing images with smart descriptions"""
    
    pdf_name = os.path.basename(mineru_output_dir)
    markdown_file = f"{mineru_output_dir}/auto/{pdf_name}.md"
    content_list_file = f"{mineru_output_dir}/auto/{pdf_name}_content_list.json"
    
    # Start with existing markdown content - PRESERVE AS IS
    markdown_content = ""
    if os.path.exists(markdown_file):
        with open(markdown_file, 'r', encoding='utf-8') as f:
            original_content = f.read()
        logger.info(f"Read {len(original_content)} characters from existing markdown")
        
        # Replace image paths with Supabase URLs WITHOUT changing alt text
        markdown_content = original_content
        for local_filename, supabase_url in image_url_map.items():
            patterns = [
                f"images/{local_filename}",
                f"./images/{local_filename}",
                f"auto/images/{local_filename}"
            ]
            for pattern in patterns:
                # Only replace the URL, preserve existing alt text
                markdown_content = markdown_content.replace(f"]({pattern})", f"]({supabase_url})")
    
    # Find which images are referenced in the ORIGINAL markdown
    image_pattern = r'!\[.*?\]\([^)]*?([^/]+\.(?:jpg|jpeg|png))[^)]*?\)'
    existing_image_matches = re.findall(image_pattern, markdown_content, re.IGNORECASE)
    images_already_in_markdown = set(match for match in existing_image_matches)
    
    logger.info(f"Found {len(images_already_in_markdown)} images already in original markdown: {images_already_in_markdown}")
    
    # Get all images from content_list with context
    all_images = extract_images_with_context(content_list_file)
    logger.info(f"Found {len(all_images)} total images in content_list.json")
    
    # Find truly missing images (not in original markdown AND uploaded to Supabase)
    missing_images = []
    for img_info in all_images:
        filename = img_info["filename"]
        # Only add if: 1) not in original markdown AND 2) was uploaded to Supabase
        if filename not in images_already_in_markdown and filename in image_url_map:
            missing_images.append(img_info)
    
    logger.info(f"Found {len(missing_images)} truly missing images to add with smart descriptions")
    
    if missing_images:
        # Add section for missing images with smart descriptions
        markdown_content += "\n\n## Additional Technical Documentation\n\n"
        
        for img_info in missing_images:
            filename = img_info["filename"]
            url = image_url_map[filename]
            
            # Generate intelligent description
            smart_description = generate_intelligent_description(img_info, img_info["context"])
            
            # Add image to markdown with smart description
            markdown_content += f"![{smart_description}]({url})\n"
            
            # Add caption and context if available
            if img_info['caption']:
                markdown_content += f"*Caption: {img_info['caption']}*\n"
            if img_info['footnote']:
                markdown_content += f"*Note: {img_info['footnote']}*\n"
            
            markdown_content += "\n"
        
        logger.info(f"Added {len(missing_images)} missing images with smart descriptions while preserving {len(images_already_in_markdown)} existing image references")
    
    return markdown_content

async def process_page_preserve_existing(page_id: int):
    """Process page while preserving existing image references"""
    try:
        logger.info(f"Processing page {page_id} while PRESERVING existing image references...")
        
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
            # Process datasheets while preserving existing images
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
                    
                    # Preserve existing and enhance with missing images
                    pdf_content = preserve_and_enhance_markdown(mineru_output_dir, image_url_map)
                    
                    # Create section for this datasheet
                    datasheet_section = f"""## Technical Documentation: {os.path.basename(datasheet['url'])}

{pdf_content}

---
"""
                    all_content_sections.append(datasheet_section)
                    logger.info(f"Added datasheet section while preserving existing images")
                    
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
*Complete content: Web page + {len(datasheets)} datasheet(s) with {len(all_images_uploaded)} images (preserving existing references)*
"""
        
        logger.info(f"Created document PRESERVING existing images: {len(combined_content)} characters, {len(all_images_uploaded)} images")
        
        # Upload to Supabase storage
        doc_url = await upload_processed_document_to_supabase(
            combined_content,
            page_data,
            {
                "processing_method": "preserve_existing_with_smart_missing",
                "datasheets_processed": len(datasheets),
                "images_uploaded": len(all_images_uploaded),
                "content_length": len(combined_content),
                "includes_web_content": True,
                "preserves_existing_images": True
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
                "file_source": f"page_{page_id}_{safe_category}_preserved"
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
        
        logger.info("PRESERVE EXISTING processing complete!")
        
        return {
            "success": True,
            "page_id": page_id,
            "content_length": len(combined_content),
            "images_uploaded": len(all_images_uploaded),
            "datasheets_processed": len(datasheets),
            "doc_url": doc_url,
            "includes_web_content": bool(web_content),
            "preserves_existing": True
        }
        
    except Exception as e:
        logger.error(f"Error processing page {page_id}: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python process_preserve_existing_images.py <page_id>")
        sys.exit(1)
    
    page_id = int(sys.argv[1])
    result = asyncio.run(process_page_preserve_existing(page_id))
    
    if result["success"]:
        print(f"""
SUCCESS! PRESERVED EXISTING IMAGES + SMART MISSING
Page ID: {result['page_id']}
Content Length: {result['content_length']:,} characters
Images Uploaded: {result['images_uploaded']}
Datasheets Processed: {result['datasheets_processed']}
Web Content Included: {'YES' if result.get('includes_web_content') else 'NO'}
Existing Images Preserved: {'YES' if result.get('preserves_existing') else 'NO'}
Document URL: {result.get('doc_url', 'N/A')}
""")
    else:
        print(f"FAILED: {result['error']}")