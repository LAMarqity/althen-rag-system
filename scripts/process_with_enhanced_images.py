#!/usr/bin/env python3
"""
Enhanced page processing with descriptive image alt text and captions
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

def extract_image_metadata(mineru_output_dir: str) -> dict:
    """Extract image metadata from MinerU content_list.json"""
    try:
        content_list_file = os.path.join(mineru_output_dir, "auto", f"{os.path.basename(mineru_output_dir)}_content_list.json")
        
        if not os.path.exists(content_list_file):
            logger.warning(f"Content list file not found: {content_list_file}")
            return {}
        
        with open(content_list_file, 'r', encoding='utf-8') as f:
            content_list = json.load(f)
        
        image_metadata = {}
        
        for item in content_list:
            if item.get("type") == "image":
                img_path = item.get("img_path", "")
                image_filename = os.path.basename(img_path)
                
                # Extract caption and context
                caption = ""
                if item.get("image_caption"):
                    caption = " ".join(item["image_caption"]).strip()
                
                footnote = ""
                if item.get("image_footnote"):
                    footnote = " ".join(item["image_footnote"]).strip()
                
                # Create descriptive context based on caption content
                description = create_image_description(caption, footnote)
                
                image_metadata[image_filename] = {
                    "caption": caption,
                    "footnote": footnote,
                    "description": description,
                    "page_idx": item.get("page_idx", 0)
                }
        
        logger.info(f"Extracted metadata for {len(image_metadata)} images")
        return image_metadata
        
    except Exception as e:
        logger.error(f"Error extracting image metadata: {e}")
        return {}

def create_image_description(caption: str, footnote: str) -> str:
    """Create descriptive alt text based on caption and content analysis"""
    
    # Combine caption and footnote
    full_text = f"{caption} {footnote}".strip().lower()
    
    # Define description patterns
    patterns = {
        "wiring": ["wiring", "wire", "cable", "connection", "pin", "connector"],
        "dimensions": ["dimension", "mm", "inch", "size", "diameter", "length", "width", "height"],
        "diagram": ["diagram", "schematic", "circuit", "drawing"],
        "chart": ["chart", "graph", "table", "specification", "spec"],
        "product_photo": ["photo", "image", "picture"],
        "mounting": ["mount", "installation", "bracket", "hole"],
        "performance": ["performance", "curve", "response", "frequency"],
        "exploded_view": ["exploded", "assembly", "parts", "component"]
    }
    
    # Check for specific patterns
    for desc_type, keywords in patterns.items():
        if any(keyword in full_text for keyword in keywords):
            if desc_type == "wiring":
                return "Wiring Diagram"
            elif desc_type == "dimensions":
                return "Dimensions and Specifications"
            elif desc_type == "diagram":
                return "Technical Diagram"
            elif desc_type == "chart":
                return "Specifications Chart"
            elif desc_type == "product_photo":
                return "Product Photo"
            elif desc_type == "mounting":
                return "Mounting Instructions"
            elif desc_type == "performance":
                return "Performance Chart"
            elif desc_type == "exploded_view":
                return "Exploded View"
    
    # If we have a caption, use it directly
    if caption.strip():
        return f"Figure: {caption.strip()}"
    
    # Default description
    return "Technical Image"

def create_descriptive_filename(base_filename: str, description: str, index: int) -> str:
    """Create a descriptive filename based on image content"""
    
    # Clean description for filename
    clean_desc = re.sub(r'[^\w\s-]', '', description.lower())
    clean_desc = re.sub(r'\s+', '_', clean_desc)
    
    # Limit length
    if len(clean_desc) > 30:
        clean_desc = clean_desc[:30]
    
    # Get file extension
    ext = os.path.splitext(base_filename)[1]
    
    return f"{clean_desc}_{index:02d}{ext}"

async def process_page_with_enhanced_images(page_id: int):
    """Process a page with enhanced image descriptions and alt text"""
    try:
        logger.info(f"Processing page {page_id} with enhanced image processing...")
        
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
            # Process each datasheet with enhanced images
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
                markdown_file = f"{mineru_output_dir}/auto/{pdf_name}.md"
                
                if os.path.exists(markdown_file):
                    # Read the rich markdown content
                    with open(markdown_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    logger.info(f"Extracted {len(content)} characters of content")
                    
                    # Extract image metadata from content_list.json
                    image_metadata = extract_image_metadata(mineru_output_dir)
                    
                    # Process images with enhanced descriptions
                    images_dir = os.path.join(mineru_output_dir, "auto", "images")
                    enhanced_content = content
                    
                    if os.path.exists(images_dir):
                        image_files = [f for f in os.listdir(images_dir) 
                                     if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                        
                        logger.info(f"Processing {len(image_files)} images with enhanced descriptions...")
                        
                        for i, image_file in enumerate(image_files):
                            image_path = os.path.join(images_dir, image_file)
                            
                            # Get metadata for this image
                            metadata = image_metadata.get(image_file, {})
                            description = metadata.get("description", "Technical Image")
                            caption = metadata.get("caption", "")
                            
                            # Create descriptive filename
                            descriptive_filename = create_descriptive_filename(
                                image_file, description, i + 1
                            )
                            
                            # Read image data
                            with open(image_path, 'rb') as img_f:
                                image_data = img_f.read()
                            
                            # Upload to Supabase with descriptive name
                            image_url = await upload_image_to_supabase(
                                image_data,
                                f"page_{page_id}_{descriptive_filename}",
                                page_id,
                                datasheet['id']
                            )
                            
                            if image_url:
                                all_images_uploaded.append(image_url)
                                
                                # Create enhanced alt text
                                alt_text = description
                                if caption:
                                    alt_text = f"{description}: {caption}"
                                
                                # Replace in markdown with enhanced alt text
                                old_img_ref = f"![](images/{image_file})"
                                new_img_ref = f"![{alt_text}]({image_url})"
                                
                                enhanced_content = enhanced_content.replace(old_img_ref, new_img_ref)
                                
                                logger.info(f"Enhanced image {i+1}: {alt_text}")
                    
                    all_content.append(enhanced_content)
                    logger.info(f"Successfully processed datasheet with enhanced image descriptions")
                    
                else:
                    logger.warning(f"No MinerU output found for {pdf_name}")
                    
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
*Processed from {len(datasheets)} datasheet(s) with {len(all_images_uploaded)} enhanced images using MinerU extraction*
"""
            else:
                return {"success": False, "error": "No content was processed"}
        
        logger.info(f"Created combined document: {len(combined_content)} characters")
        
        # Upload to Supabase storage
        doc_url = await upload_processed_document_to_supabase(
            combined_content,
            page_data,
            {
                "processing_method": "enhanced_image_extraction",
                "datasheets_processed": len(datasheets),
                "images_uploaded": len(all_images_uploaded),
                "content_length": len(combined_content),
                "enhanced_images": True
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
                "file_source": f"page_{page_id}_{page_data.get('category', 'content').lower().replace(' ', '_')}_enhanced"
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
            "enhanced_images": True
        }
        
    except Exception as e:
        logger.error(f"Error processing page {page_id}: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python process_with_enhanced_images.py <page_id>")
        sys.exit(1)
    
    page_id = int(sys.argv[1])
    result = asyncio.run(process_page_with_enhanced_images(page_id))
    
    if result["success"]:
        print(f"""
🎉 SUCCESS! Enhanced Image Processing
Page ID: {result['page_id']}
Content Length: {result['content_length']:,} characters
Enhanced Images: {result['images_uploaded']}
Datasheets Processed: {result['datasheets_processed']}
Document URL: {result.get('doc_url', 'N/A')}
""")
    else:
        print(f"❌ FAILED: {result['error']}")