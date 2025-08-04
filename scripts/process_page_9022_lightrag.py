#!/usr/bin/env python3
"""
Enhanced page processing that extracts actual MinerU markdown content with images
"""
import os
import sys
import asyncio
import glob
import json
import shutil
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.raganything_api_service import (
    get_supabase_client, 
    logger,
    upload_image_to_supabase,
    upload_processed_document_to_supabase,
    initialize_rag
)

# Global variable for RAG instance
rag_instance = None

async def extract_mineru_content(pdf_path: str) -> dict:
    """Extract the actual processed markdown content from MinerU output"""
    try:
        pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
        
        # Look for the MinerU output directory
        output_patterns = [
            f"output/{pdf_name}/auto/{pdf_name}.md",
            f"output/*/auto/{pdf_name}.md",
            f"output/*/auto/*.md"
        ]
        
        markdown_file = None
        for pattern in output_patterns:
            files = glob.glob(pattern)
            if files:
                # Find the best match
                for f in files:
                    if pdf_name in os.path.basename(f):
                        markdown_file = f
                        break
                if markdown_file:
                    break
        
        if not markdown_file or not os.path.exists(markdown_file):
            return {"success": False, "error": "No MinerU markdown file found"}
            
        logger.info(f"Found MinerU markdown: {markdown_file}")
        
        # Read the processed markdown content
        with open(markdown_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Find images directory
        images_dir = os.path.join(os.path.dirname(markdown_file), 'images')
        image_files = []
        
        if os.path.exists(images_dir):
            image_files = [
                os.path.join(images_dir, f) 
                for f in os.listdir(images_dir)
                if f.lower().endswith(('.jpg', '.jpeg', '.png'))
            ]
            
        logger.info(f"Extracted {len(content)} chars and {len(image_files)} images")
        
        return {
            "success": True,
            "content": content,
            "image_files": image_files,
            "images_dir": images_dir
        }
        
    except Exception as e:
        logger.error(f"Error extracting MinerU content: {e}")
        return {"success": False, "error": str(e)}

async def process_page_with_mineru_extraction(page_id: int):
    """Process a page using actual MinerU content extraction"""
    global rag_instance
    
    # Initialize connections
    supabase_client = get_supabase_client()
    rag_instance = await initialize_rag()
    
    # Get page data
    page_response = supabase_client.table("new_pages_index").select("*").eq("id", page_id).execute()
    if not page_response.data:
        logger.error(f"Page {page_id} not found")
        return
        
    page_data = page_response.data[0]
    logger.info(f"Processing page: {page_data['title']}")
    
    # Get datasheets
    datasheets_response = supabase_client.table("new_datasheets_index").select("*").eq("page_id", page_id).execute()
    datasheets = datasheets_response.data
    
    if not datasheets:
        logger.info("No datasheets found")
        return
        
    # Process each datasheet
    all_content = []
    all_images = []
    
    for datasheet in datasheets:
        logger.info(f"Processing datasheet: {datasheet['filename']}")
        
        # Download PDF
        import tempfile
        import requests
        
        response = requests.get(datasheet['url'])
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            tmp_file.write(response.content)
            pdf_path = tmp_file.name
        
        try:
            # Process with RAGAnything (this generates MinerU output)
            await rag_instance.process_document_complete(
                pdf_path,
                doc_id=f"page_{page_id}_datasheet_{datasheet['id']}"
            )
            
            # Extract the actual MinerU content
            mineru_result = await extract_mineru_content(pdf_path)
            
            if mineru_result["success"]:
                # Get the rich markdown content
                content = mineru_result["content"]
                images = mineru_result["image_files"]
                
                # Upload images to Supabase and replace paths in markdown
                image_url_map = {}
                for image_path in images:
                    if os.path.exists(image_path):
                        # Read image data
                        with open(image_path, 'rb') as img_file:
                            image_data = img_file.read()
                        
                        # Upload to Supabase
                        image_filename = os.path.basename(image_path)
                        image_url = await upload_image_to_supabase(
                            image_data, 
                            image_filename, 
                            page_id, 
                            datasheet['id']
                        )
                        
                        if image_url:
                            # Map local path to Supabase URL
                            relative_path = f"images/{image_filename}"
                            image_url_map[relative_path] = image_url
                            all_images.append(image_url)
                
                # Replace image paths in markdown
                processed_content = content
                for local_path, supabase_url in image_url_map.items():
                    processed_content = processed_content.replace(f"images/{os.path.basename(local_path)}", supabase_url)
                    processed_content = processed_content.replace(local_path, supabase_url)
                
                all_content.append(processed_content)
                logger.info(f"Successfully processed datasheet with {len(images)} images")
                
            else:
                logger.warning(f"Failed to extract MinerU content: {mineru_result['error']}")
                
        finally:
            # Clean up
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
    
    # Combine all content
    if all_content:
        combined_content = f"""# {page_data['title']}

**URL:** {page_data['url']}
**Business Area:** {page_data['business_area']}
**Page Type:** {page_data['page_type']}

---

{"".join(all_content)}

---
*Processed from {len(datasheets)} datasheet(s) with {len(all_images)} images*
"""
        
        # Upload combined document
        doc_url = await upload_processed_document_to_supabase(
            combined_content,
            page_data,
            {
                "processing_method": "mineru_extraction",
                "datasheets_processed": len(datasheets),
                "images_uploaded": len(all_images)
            }
        )
        
        if doc_url:
            logger.info(f"Document uploaded: {doc_url}")
        
        # Upload to LightRAG
        if rag_instance:
            await rag_instance.insert_document(combined_content, f"page_{page_id}")
            logger.info("Uploaded to LightRAG")
        
        # Mark as processed
        supabase_client.table("new_pages_index").update({
            "rag_processed": True,
            "rag_processed_at": "now()"
        }).eq("id", page_id).execute()
        
        logger.info("Page marked as processed")
        
        return {
            "status": "success",
            "content_length": len(combined_content),
            "images_uploaded": len(all_images),
            "doc_url": doc_url
        }
    
    else:
        logger.error("No content was successfully processed")
        return {"status": "failed", "error": "No content processed"}

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python process_page_9022_lightrag.py <page_id>")
        sys.exit(1)
    
    page_id = int(sys.argv[1])
    result = asyncio.run(process_page_with_mineru_extraction(page_id))
    print(f"Result: {result}")