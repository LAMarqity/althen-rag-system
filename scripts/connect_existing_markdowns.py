#!/usr/bin/env python3
"""
Connect existing markdown files to new_pages_index table retroactively
This script finds existing processed markdown files and uploads them to Supabase storage
with proper connections to the pages table
"""
import os
import sys
import json
import re
import glob
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.raganything_api_service import (
    get_supabase_client,
    logger,
    upload_processed_document_to_supabase
)

def extract_page_id_from_path(file_path: str) -> int:
    """Extract page ID from file path like knowledge_base/page_9067/..."""
    match = re.search(r'page_(\d+)', file_path)
    if match:
        return int(match.group(1))
    return None

def find_existing_markdown_files() -> list:
    """Find all existing processed markdown files"""
    markdown_files = []
    
    # Pattern 1: knowledge_base/page_*/*/auto/*.md
    pattern1 = "knowledge_base/page_*/*/auto/*.md"
    files1 = glob.glob(pattern1, recursive=True)
    
    # Pattern 2: output/*/auto/*.md (recent processing)
    pattern2 = "output/*/auto/*.md"
    files2 = glob.glob(pattern2, recursive=True)
    
    # Pattern 3: scripts/knowledge_base/page_*/*/auto/*.md
    pattern3 = "scripts/knowledge_base/page_*/*/auto/*.md"
    files3 = glob.glob(pattern3, recursive=True)
    
    all_files = files1 + files2 + files3
    
    for file_path in all_files:
        page_id = extract_page_id_from_path(file_path)
        if page_id:
            markdown_files.append({
                "file_path": file_path,
                "page_id": page_id,
                "file_size": os.path.getsize(file_path),
                "modified_time": datetime.fromtimestamp(os.path.getmtime(file_path))
            })
    
    return markdown_files

def get_page_data_from_db(page_id: int) -> dict:
    """Get page data from new_pages_index table"""
    try:
        supabase_client = get_supabase_client()
        response = supabase_client.table("new_pages_index").select("*").eq("id", page_id).execute()
        
        if response.data:
            return response.data[0]
        else:
            logger.warning(f"Page {page_id} not found in database")
            return None
    except Exception as e:
        logger.error(f"Error fetching page {page_id}: {e}")
        return None

def create_enhanced_markdown_with_metadata(original_content: str, page_data: dict, file_info: dict) -> str:
    """Create enhanced markdown with proper metadata header"""
    
    page_id = page_data.get('id')
    url = page_data.get('url', '')
    
    # Create URL-based name
    url_parts = url.rstrip('/').split('/')
    page_name = url_parts[-1] if url_parts else f"page_{page_id}"
    
    # Create metadata header
    metadata_header = f"""---
title: "{page_data.get('image_title', page_name)}"
page_id: {page_id}
url: "{url}"
business_area: "{page_data.get('business_area', '')}"
category: "{page_data.get('category', '')}"
subcategory: "{page_data.get('subcategory', '')}"
page_type: "{page_data.get('page_type', '')}"
processed_at: "{file_info['modified_time'].isoformat()}"
retroactive_connection: true
original_file_path: "{file_info['file_path']}"
processing_metadata: {{
    "method": "retroactive_connection",
    "original_file_size": {file_info['file_size']},
    "connected_at": "{datetime.now().isoformat()}"
}}
---

"""
    
    return metadata_header + original_content

async def connect_markdown_to_page(file_info: dict) -> dict:
    """Connect a single markdown file to its page in the database"""
    try:
        page_id = file_info['page_id']
        file_path = file_info['file_path']
        
        logger.info(f"Processing markdown for page {page_id}: {file_path}")
        
        # Get page data from database
        page_data = get_page_data_from_db(page_id)
        if not page_data:
            return {"success": False, "error": f"Page {page_id} not found in database"}
        
        # Read original markdown content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
        except Exception as e:
            return {"success": False, "error": f"Could not read file: {e}"}
        
        # Create enhanced markdown with metadata
        enhanced_content = create_enhanced_markdown_with_metadata(
            original_content, 
            page_data, 
            file_info
        )
        
        # Upload to Supabase storage using existing function
        processing_metadata = {
            "method": "retroactive_connection",
            "original_file_path": file_path,
            "original_file_size": file_info['file_size'],
            "connected_at": datetime.now().isoformat(),
            "content_length": len(enhanced_content)
        }
        
        doc_url = await upload_processed_document_to_supabase(
            enhanced_content,
            page_data,
            processing_metadata
        )
        
        if doc_url:
            # Update page status if not already marked as processed
            supabase_client = get_supabase_client()
            
            # Check current status
            current_status = page_data.get('rag_ingestion_status')
            if current_status != 'completed':
                update_data = {
                    "rag_ingested": True,
                    "rag_ingested_at": "now()",
                    "rag_ingestion_status": "completed"
                }
                
                supabase_client.table("new_pages_index").update(update_data).eq("id", page_id).execute()
                logger.info(f"Updated page {page_id} status to completed")
            
            return {
                "success": True,
                "page_id": page_id,
                "doc_url": doc_url,
                "content_length": len(enhanced_content),
                "original_file": file_path
            }
        else:
            return {"success": False, "error": "Failed to upload to Supabase storage"}
            
    except Exception as e:
        logger.error(f"Error connecting markdown for page {page_id}: {e}")
        return {"success": False, "error": str(e)}

async def connect_all_existing_markdowns():
    """Main function to connect all existing markdown files"""
    logger.info("🔗 Starting retroactive markdown connection process...")
    
    # Find all existing markdown files
    markdown_files = find_existing_markdown_files()
    logger.info(f"Found {len(markdown_files)} existing markdown files")
    
    results = {
        "total_files": len(markdown_files),
        "successful": 0,
        "failed": 0,
        "details": []
    }
    
    for i, file_info in enumerate(markdown_files, 1):
        logger.info(f"Processing {i}/{len(markdown_files)}: Page {file_info['page_id']}")
        
        result = await connect_markdown_to_page(file_info)
        results["details"].append(result)
        
        if result["success"]:
            results["successful"] += 1
            logger.info(f"✅ Successfully connected page {result['page_id']}")
        else:
            results["failed"] += 1
            logger.error(f"❌ Failed to connect page {file_info['page_id']}: {result['error']}")
    
    # Summary
    logger.info("=" * 50)
    logger.info("🎯 RETROACTIVE CONNECTION SUMMARY")
    logger.info("=" * 50)
    logger.info(f"Total files found: {results['total_files']}")
    logger.info(f"Successfully connected: {results['successful']}")
    logger.info(f"Failed: {results['failed']}")
    
    if results["successful"] > 0:
        logger.info("\n✅ Successfully connected pages:")
        for detail in results["details"]:
            if detail["success"]:
                logger.info(f"  Page {detail['page_id']}: {detail['doc_url']}")
    
    if results["failed"] > 0:
        logger.info("\n❌ Failed connections:")
        for detail in results["details"]:
            if not detail["success"]:
                logger.info(f"  Page {detail.get('page_id', 'unknown')}: {detail['error']}")
    
    return results

if __name__ == "__main__":
    import asyncio
    
    print("🔗 RETROACTIVE MARKDOWN CONNECTION")
    print("This script will connect existing markdown files to the new_pages_index table")
    print("by uploading them to Supabase storage with proper metadata.")
    print()
    
    # Run the connection process
    results = asyncio.run(connect_all_existing_markdowns())
    
    print(f"\n🏁 Process complete!")
    print(f"✅ {results['successful']} files connected successfully")
    print(f"❌ {results['failed']} files failed to connect")