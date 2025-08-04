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
import traceback
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.raganything_api_service import (
    get_supabase_client,
    logger,
    initialize_rag,
    rag_instance
)

async def main():
    """Main processing function"""
    try:
        page_id = 9272
        
        logger.info("Starting enhanced MinerU test...")
        
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
        logger.info(f"Found page data: {list(page_data.keys())}")
        page_title = page_data.get('title') or page_data.get('name') or page_data.get('url', 'Unknown')
        logger.info(f"Found page: {page_title}")
        
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
        logger.info("Downloading PDF...")
        response = requests.get(datasheet['url'])
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            tmp_file.write(response.content)
            pdf_path = tmp_file.name
        
        logger.info(f"Downloaded PDF to: {pdf_path}")
        
        try:
            # Process with RAGAnything to generate MinerU output
            logger.info("Processing with RAGAnything...")
            await rag_instance.process_document_complete(
                pdf_path,
                doc_id=f"page_{page_id}_datasheet_{datasheet['id']}"
            )
            logger.info("RAGAnything processing completed")
            
            # Look for the generated markdown file
            pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
            logger.info(f"Looking for MinerU output for: {pdf_name}")
            
            output_patterns = [
                f"output/{pdf_name}/auto/{pdf_name}.md",
                f"output/*/auto/{pdf_name}.md",
                f"output/*/auto/*.md"
            ]
            
            markdown_file = None
            for pattern in output_patterns:
                logger.info(f"Checking pattern: {pattern}")
                files = glob.glob(pattern)
                if files:
                    logger.info(f"Found files: {files}")
                    markdown_file = files[0]
                    break
            
            if markdown_file and os.path.exists(markdown_file):
                logger.info(f"SUCCESS! Found MinerU output: {markdown_file}")
                
                # Read the processed content
                with open(markdown_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                logger.info(f"Content length: {len(content)} characters")
                
                # Show first 1000 characters
                print("\n" + "="*60)
                print("EXTRACTED MINERU CONTENT:")
                print("="*60)
                print(content[:1000])
                if len(content) > 1000:
                    print(f"\n... ({len(content)-1000} more characters)")
                print("="*60)
                
                # Check for images
                images_dir = os.path.join(os.path.dirname(markdown_file), 'images')
                if os.path.exists(images_dir):
                    image_files = os.listdir(images_dir)
                    logger.info(f"Found {len(image_files)} images")
                    
                    # Show first few image filenames
                    print("\nIMAGES FOUND:")
                    for i, img in enumerate(image_files[:5]):
                        print(f"  {i+1}. {img}")
                    if len(image_files) > 5:
                        print(f"  ... and {len(image_files)-5} more images")
                
                return {"success": True, "content_length": len(content), "images": len(image_files) if os.path.exists(images_dir) else 0}
                
            else:
                logger.error("FAILED! No MinerU markdown output found")
                logger.info("Checking what files were created...")
                
                # Check output directory
                if os.path.exists("output"):
                    for root, dirs, files in os.walk("output"):
                        for file in files:
                            logger.info(f"  Found: {os.path.join(root, file)}")
                        
                return {"success": False, "error": "No markdown output"}
                
        finally:
            # Clean up
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
                logger.info("Cleaned up temporary PDF")
    
    except Exception as e:
        logger.error(f"Error in main function: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    result = asyncio.run(main())
    print(f"\nFINAL RESULT: {result}")