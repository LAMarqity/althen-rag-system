#!/usr/bin/env python3
"""
Simple test to process page 9272 with enhanced MinerU content extraction
"""
import os
import sys
import asyncio
import glob
import json
import tempfile
import requests
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import everything we need
sys.path.append('/workspace/althen-rag-system')
from scripts.raganything_api_service import (
    get_supabase_client,
    logger,
    upload_image_to_supabase,
    initialize_rag,
    rag_instance
)

async def main():
    """Main processing function"""
    try:
        page_id = 9272
        
        # Initialize
        logger.info("Initializing connections...")
        supabase_client = get_supabase_client()
        await initialize_rag()
        
        # Get page data
        logger.info(f"Getting page data for {page_id}...")
        page_response = supabase_client.table("new_pages_index").select("*").eq("id", page_id).execute()
        if not page_response.data:
            logger.error(f"Page {page_id} not found")
            return
            
        page_data = page_response.data[0]
        logger.info(f"Found page: {page_data['title']}")
        
        # Get datasheets
        datasheets_response = supabase_client.table("new_datasheets_index").select("*").eq("page_id", page_id).execute()
        datasheets = datasheets_response.data
        logger.info(f"Found {len(datasheets)} datasheets")
        
        if not datasheets:
            logger.error("No datasheets found")
            return
        
        # Process first datasheet
        datasheet = datasheets[0]
    logger.info(f"Processing datasheet: {datasheet['filename']}")
    
    # Download PDF
    response = requests.get(datasheet['url'])
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
        tmp_file.write(response.content)
        pdf_path = tmp_file.name
    
    try:
        # Process with RAGAnything to generate MinerU output
        logger.info("Processing with RAGAnything...")
        await rag_instance.process_document_complete(
            pdf_path,
            doc_id=f"page_{page_id}_datasheet_{datasheet['id']}"
        )
        
        # Look for the generated markdown file
        pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
        output_patterns = [
            f"output/{pdf_name}/auto/{pdf_name}.md",
            f"output/*/auto/{pdf_name}.md",
            f"output/*/auto/*.md"
        ]
        
        markdown_file = None
        for pattern in output_patterns:
            files = glob.glob(pattern)
            if files:
                markdown_file = files[0]
                break
        
        if markdown_file and os.path.exists(markdown_file):
            logger.info(f"Found MinerU output: {markdown_file}")
            
            # Read the processed content
            with open(markdown_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            logger.info(f"Content length: {len(content)} characters")
            logger.info("First 500 characters:")
            print("=" * 50)
            print(content[:500])
            print("=" * 50)
            
            # Check for images
            images_dir = os.path.join(os.path.dirname(markdown_file), 'images')
            if os.path.exists(images_dir):
                image_files = os.listdir(images_dir)
                logger.info(f"Found {len(image_files)} images")
                
                # Show first few image filenames
                for i, img in enumerate(image_files[:5]):
                    logger.info(f"  Image {i+1}: {img}")
            
        else:
            logger.error("No MinerU markdown output found")
            
    finally:
        # Clean up
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)

if __name__ == "__main__":
    asyncio.run(main())