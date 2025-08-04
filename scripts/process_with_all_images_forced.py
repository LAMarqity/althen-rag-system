#!/usr/bin/env python3
"""
Enhanced processing that forces ALL extracted images into markdown
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

def create_comprehensive_markdown_from_content_list(content_list_file: str, images_dir: str, image_url_map: dict) -> str:
    """Create markdown that includes ALL images and content from content_list.json"""
    try:
        with open(content_list_file, 'r', encoding='utf-8') as f:
            content_list = json.load(f)
        
        markdown_sections = []
        current_section = []
        
        for item in content_list:
            item_type = item.get("type", "")
            
            if item_type == "image":
                # Force ALL images into markdown
                img_path = item.get("img_path", "")
                image_filename = os.path.basename(img_path)
                image_caption = " ".join(item.get("image_caption", [])).strip()
                image_footnote = " ".join(item.get("image_footnote", [])).strip()
                
                # Get Supabase URL
                supabase_url = image_url_map.get(image_filename, f"images/{image_filename}")
                
                # Create descriptive alt text
                alt_text = create_image_description(image_caption, image_footnote)
                if image_caption:
                    alt_text = f"{alt_text}: {image_caption}"
                
                # Add image to markdown
                current_section.append(f"\n![{alt_text}]({supabase_url})\n")
                
                if image_caption:
                    current_section.append(f"*{image_caption}*\n")
                if image_footnote:
                    current_section.append(f"*Note: {image_footnote}*\n")
            
            elif item_type == "table":
                # Force table images into markdown
                img_path = item.get("img_path", "")
                if img_path:
                    image_filename = os.path.basename(img_path)
                    supabase_url = image_url_map.get(image_filename, f"images/{image_filename}")
                    
                    table_caption = " ".join(item.get("table_caption", [])).strip()
                    alt_text = f"Table: {table_caption}" if table_caption else "Data Table"
                    
                    current_section.append(f"\n![{alt_text}]({supabase_url})\n")
                    if table_caption:
                        current_section.append(f"*{table_caption}*\n")
                
                # Also include table HTML if available
                table_body = item.get("table_body", "")
                if table_body:
                    current_section.append(f"\n{table_body}\n")
            
            elif item_type == "text":
                # Add text content
                text = item.get("text", "").strip()
                if text:
                    text_level = item.get("text_level", 0)
                    
                    # Format as heading if it has a level
                    if text_level > 0:
                        heading_prefix = "#" * min(text_level + 1, 6)  # Max 6 levels
                        current_section.append(f"\n{heading_prefix} {text}\n")
                    else:
                        current_section.append(f"{text}\n\n")
        
        # Combine all sections
        comprehensive_markdown = "".join(current_section)
        
        logger.info(f"Created comprehensive markdown with ALL images forced: {len(comprehensive_markdown)} characters")
        return comprehensive_markdown
        
    except Exception as e:
        logger.error(f"Error creating comprehensive markdown: {e}")
        return ""

def create_image_description(caption: str, footnote: str) -> str:
    """Create descriptive alt text based on caption and content analysis"""
    
    # Combine caption and footnote
    full_text = f"{caption} {footnote}".strip().lower()
    
    # Define description patterns
    patterns = {
        "table": ["table", "data", "specification", "specs", "dimensions", "parameters"],
        "wiring": ["wiring", "wire", "cable", "connection", "pin", "connector"],
        "dimensions": ["dimension", "mm", "inch", "size", "diameter", "length", "width", "height"],
        "diagram": ["diagram", "schematic", "circuit", "drawing"],
        "chart": ["chart", "graph", "curve", "performance"],
        "product_photo": ["photo", "image", "picture"],
        "mounting": ["mount", "installation", "bracket", "hole"],
        "exploded_view": ["exploded", "assembly", "parts", "component"]
    }
    
    # Check for specific patterns
    for desc_type, keywords in patterns.items():
        if any(keyword in full_text for keyword in keywords):
            if desc_type == "table":
                return "Data Table"
            elif desc_type == "wiring":
                return "Wiring Diagram"
            elif desc_type == "dimensions":
                return "Dimensions Chart"
            elif desc_type == "diagram":
                return "Technical Diagram"
            elif desc_type == "chart":
                return "Performance Chart"
            elif desc_type == "product_photo":
                return "Product Photo"
            elif desc_type == "mounting":
                return "Mounting Diagram"
            elif desc_type == "exploded_view":
                return "Exploded View"
    
    # If we have a caption, use it directly
    if caption.strip():
        return f"Figure"
    
    # Default description
    return "Technical Image"

async def process_page_with_forced_images(page_id: int):
    """Process a page forcing ALL extracted images into markdown"""
    try:
        logger.info(f"Processing page {page_id} with ALL images forced into markdown...")
        
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
        lightrag_track_id = None
        
        if not datasheets:
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
        
        else:
            # Process each datasheet with ALL images forced
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
                    
                    # Extract MinerU content and metadata
                    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
                    mineru_output_dir = f"output/{pdf_name}"
                    content_list_file = f"{mineru_output_dir}/auto/{pdf_name}_content_list.json"
                    
                    if os.path.exists(content_list_file):
                        logger.info(f"Processing with ALL images forced from content_list.json")
                        
                        # Process images and upload to Supabase
                        images_dir = os.path.join(mineru_output_dir, "auto", "images")
                        image_url_map = {}
                        
                        if os.path.exists(images_dir):
                            image_files = [f for f in os.listdir(images_dir) 
                                         if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                            
                            logger.info(f"Uploading ALL {len(image_files)} images to Supabase...")
                            
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
                                    image_url_map[image_file] = image_url
                                    all_images_uploaded.append(image_url)
                                    
                                    if (i + 1) % 10 == 0:
                                        logger.info(f"Uploaded {i+1}/{len(image_files)} images")
                        
                        # Create comprehensive markdown with ALL images
                        comprehensive_content = create_comprehensive_markdown_from_content_list(
                            content_list_file, 
                            images_dir, 
                            image_url_map
                        )
                        
                        if comprehensive_content:
                            all_content.append(comprehensive_content)
                            logger.info(f"Successfully created comprehensive content with ALL {len(image_url_map)} images")
                        else:
                            logger.warning("Failed to create comprehensive content")
                    
                    else:
                        logger.warning(f"No content_list.json found for {pdf_name}")
                        
                finally:
                    # Clean up
                    if os.path.exists(pdf_path):
                        os.unlink(pdf_path)
            
            if all_content:
                # Create combined document from datasheets
                combined_content = f"""# {page_data.get('category', 'Product')} - {page_data.get('subcategory', 'Technical Documentation')}

**URL:** {page_url}
**Business Area:** {page_data.get('business_area', 'sensors')}
**Page Type:** {page_data.get('page_type', 'product')}

---

{"".join(all_content)}

---
*Processed from {len(datasheets)} datasheet(s) with ALL {len(all_images_uploaded)} images forced into markdown*
"""
            else:
                return {"success": False, "error": "No content was processed"}
        
        logger.info(f"Created combined document: {len(combined_content)} characters with {len(all_images_uploaded)} images")
        
        # Upload to Supabase storage
        doc_url = await upload_processed_document_to_supabase(
            combined_content,
            page_data,
            {
                "processing_method": "forced_all_images_extraction",
                "datasheets_processed": len(datasheets),
                "images_uploaded": len(all_images_uploaded),
                "content_length": len(combined_content),
                "all_images_forced": True
            }
        )
        
        # Upload to LightRAG server via API
        try:
            lightrag_server_url = os.getenv("LIGHTRAG_SERVER_URL", "http://localhost:8020")
            lightrag_api_key = os.getenv("LIGHTRAG_API_KEY")
            
            headers = {'Content-Type': 'application/json'}
            if lightrag_api_key:
                headers['X-API-Key'] = lightrag_api_key
            
            # Create safe file source name
            category = page_data.get('category') or 'content'
            safe_category = str(category).lower().replace(' ', '_').replace('-', '_')
            
            payload = {
                "text": combined_content,
                "file_source": f"page_{page_id}_{safe_category}_all_images"
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
        
        # Mark page as processed with LightRAG track_id
        page_update_data = {
            "rag_ingested": True,
            "rag_ingested_at": "now()"
        }
        if lightrag_track_id and lightrag_track_id != 'N/A':
            page_update_data["lightrag_track_id"] = lightrag_track_id
            
        supabase_client.table("new_pages_index").update(page_update_data).eq("id", page_id).execute()
        
        # Mark associated datasheets as processed
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
        
        logger.info("Page marked as processed")
        
        return {
            "success": True,
            "page_id": page_id,
            "content_length": len(combined_content),
            "images_uploaded": len(all_images_uploaded),
            "datasheets_processed": len(datasheets),
            "doc_url": doc_url,
            "all_images_forced": True
        }
        
    except Exception as e:
        logger.error(f"Error processing page {page_id}: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python process_with_all_images_forced.py <page_id>")
        sys.exit(1)
    
    page_id = int(sys.argv[1])
    result = asyncio.run(process_page_with_forced_images(page_id))
    
    if result["success"]:
        print(f"""
🎉 SUCCESS! ALL Images Forced Into Markdown
Page ID: {result['page_id']}
Content Length: {result['content_length']:,} characters
ALL Images Uploaded: {result['images_uploaded']}
Datasheets Processed: {result['datasheets_processed']}
Document URL: {result.get('doc_url', 'N/A')}
""")
    else:
        print(f"❌ FAILED: {result['error']}")