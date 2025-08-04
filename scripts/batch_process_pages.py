#!/usr/bin/env python3
"""
Batch process unprocessed pages automatically
"""
import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.raganything_api_service import get_supabase_client, logger

async def get_unprocessed_pages(limit=5):
    """Get pages that haven't been processed yet"""
    try:
        supabase = get_supabase_client()
        
        # Get unprocessed pages (rag_ingested = False or null)
        response = supabase.table("new_pages_index")\
            .select("*")\
            .or_("rag_ingested.eq.false,rag_ingested.is.null")\
            .limit(limit)\
            .execute()
        
        pages = response.data if response.data else []
        
        # Filter to only pages with datasheets if needed
        pages_with_datasheets = []
        for page in pages:
            # Check if page has datasheets
            datasheet_response = supabase.table("new_datasheets_index")\
                .select("id")\
                .eq("parent_url", page['url'])\
                .limit(1)\
                .execute()
            
            if datasheet_response.data:
                pages_with_datasheets.append(page)
                logger.info(f"Page {page['id']} has {len(datasheet_response.data)} datasheet(s)")
            else:
                # Still process pages without datasheets (web content only)
                pages_with_datasheets.append(page)
                logger.info(f"Page {page['id']} has no datasheets (web content only)")
        
        return pages_with_datasheets
        
    except Exception as e:
        logger.error(f"Error fetching unprocessed pages: {e}")
        return []

async def process_batch():
    """Process a batch of pages"""
    from scripts.process_enhance_alt_text import process_page_enhance_alt_text
    
    # Get unprocessed pages
    pages = await get_unprocessed_pages(limit=3)  # Process 3 at a time
    
    if not pages:
        logger.info("No unprocessed pages found")
        return {"processed": 0, "success": 0, "failed": 0}
    
    logger.info(f"Starting batch processing of {len(pages)} pages")
    
    results = {"processed": 0, "success": 0, "failed": 0}
    
    for page in pages:
        try:
            logger.info(f"Processing page {page['id']}: {page['url'][:50]}...")
            result = await process_page_enhance_alt_text(page['id'])
            
            results["processed"] += 1
            
            if result['success']:
                results["success"] += 1
                logger.info(f"✅ Successfully processed page {page['id']}")
                logger.info(f"   - Content length: {result.get('content_length', 0):,} chars")
                logger.info(f"   - Images uploaded: {result.get('images_uploaded', 0)}")
                logger.info(f"   - Datasheets: {result.get('datasheets_processed', 0)}")
            else:
                results["failed"] += 1
                logger.error(f"❌ Failed to process page {page['id']}: {result.get('error')}")
                
        except Exception as e:
            results["failed"] += 1
            logger.error(f"Error processing page {page['id']}: {e}")
            continue
        
        # Small delay between pages to avoid overwhelming services
        await asyncio.sleep(2)
    
    logger.info(f"Batch complete: Processed {results['processed']}, Success {results['success']}, Failed {results['failed']}")
    return results

async def check_processing_status():
    """Check overall processing status"""
    try:
        supabase = get_supabase_client()
        
        # Get counts
        total_response = supabase.table("new_pages_index").select("id", count="exact").execute()
        processed_response = supabase.table("new_pages_index").select("id", count="exact").eq("rag_ingested", True).execute()
        
        total = total_response.count if hasattr(total_response, 'count') else len(total_response.data)
        processed = processed_response.count if hasattr(processed_response, 'count') else len(processed_response.data)
        remaining = total - processed
        
        logger.info(f"📊 Processing Status: {processed}/{total} pages processed ({remaining} remaining)")
        
        if remaining > 0:
            # Estimate time
            pages_per_batch = 3
            minutes_per_batch = 5  # If running every 5 minutes
            estimated_batches = (remaining + pages_per_batch - 1) // pages_per_batch
            estimated_minutes = estimated_batches * minutes_per_batch
            estimated_hours = estimated_minutes / 60
            
            logger.info(f"⏱️ Estimated time to complete: {estimated_hours:.1f} hours ({estimated_batches} batches)")
        
        return {"total": total, "processed": processed, "remaining": remaining}
        
    except Exception as e:
        logger.error(f"Error checking status: {e}")
        return {"total": 0, "processed": 0, "remaining": 0}

if __name__ == "__main__":
    # Configure logging
    log_file = '/workspace/althen-rag-system/batch_process.log' if os.path.exists('/workspace') else 'batch_process.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, mode='a'),
            logging.StreamHandler()
        ]
    )
    
    # Add timestamp separator
    logger.info("=" * 60)
    logger.info(f"Batch processing started at {datetime.now()}")
    
    # Check status first
    asyncio.run(check_processing_status())
    
    # Process batch
    results = asyncio.run(process_batch())
    
    logger.info(f"Batch processing ended at {datetime.now()}")
    logger.info("=" * 60)