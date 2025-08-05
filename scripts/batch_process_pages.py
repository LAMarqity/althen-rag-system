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

async def get_unprocessed_pages(limit=5, subcategory=None, datasheet_count=None):
    """
    Get pages that haven't been processed yet with specific filters
    
    Args:
        limit: Maximum number of pages to return
        subcategory: Filter by subcategory (e.g., 'miniature-force-sensors')
        datasheet_count: Filter by exact number of datasheets (e.g., 1 for single datasheet)
    """
    try:
        supabase = get_supabase_client()
        
        # Build query for unprocessed pages
        query = supabase.table("new_pages_index")\
            .select("*")\
            .or_("rag_ingested.eq.false,rag_ingested.is.null")
        
        # Add subcategory filter if specified
        if subcategory:
            query = query.eq("subcategory", subcategory)
            logger.info(f"Filtering for subcategory: {subcategory}")
        
        # Get pages
        response = query.limit(limit * 3).execute()  # Get more to filter by datasheet count
        pages = response.data if response.data else []
        
        # Filter by datasheet count if specified
        filtered_pages = []
        for page in pages:
            # Count datasheets for this page
            datasheet_response = supabase.table("new_datasheets_index")\
                .select("id", count="exact")\
                .eq("parent_url", page['url'])\
                .execute()
            
            actual_count = len(datasheet_response.data) if datasheet_response.data else 0
            
            # Apply datasheet count filter if specified
            if datasheet_count is not None:
                if actual_count == datasheet_count:
                    filtered_pages.append(page)
                    if datasheet_count == 0:
                        logger.info(f"Page {page['id']} ({page.get('subcategory', 'unknown')}) has NO datasheets (web content only)")
                    else:
                        logger.info(f"Page {page['id']} ({page.get('subcategory', 'unknown')}) has exactly {actual_count} datasheet(s)")
            else:
                # No datasheet filter, include all
                filtered_pages.append(page)
                logger.info(f"Page {page['id']} ({page.get('subcategory', 'unknown')}) has {actual_count} datasheet(s)")
            
            # Stop if we have enough pages
            if len(filtered_pages) >= limit:
                break
        
        logger.info(f"Found {len(filtered_pages)} pages matching criteria")
        return filtered_pages
        
    except Exception as e:
        logger.error(f"Error fetching unprocessed pages: {e}")
        return []

async def process_batch(subcategory=None, datasheet_count=None, batch_size=3):
    """
    Process a batch of pages with optional filters
    
    Args:
        subcategory: Filter by subcategory (e.g., 'miniature-force-sensors')
        datasheet_count: Filter by exact number of datasheets (e.g., 1)
        batch_size: Number of pages to process in this batch
    """
    from scripts.process_enhance_alt_text import process_page_enhance_alt_text
    
    # Get unprocessed pages with filters
    pages = await get_unprocessed_pages(
        limit=batch_size,
        subcategory=subcategory,
        datasheet_count=datasheet_count
    )
    
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

async def check_processing_status(subcategory=None):
    """Check overall processing status with optional filtering"""
    try:
        supabase = get_supabase_client()
        
        # Build queries with optional subcategory filter
        total_query = supabase.table("new_pages_index").select("id", count="exact")
        processed_query = supabase.table("new_pages_index").select("id", count="exact").eq("rag_ingested", True)
        
        if subcategory:
            total_query = total_query.eq("subcategory", subcategory)
            processed_query = processed_query.eq("subcategory", subcategory)
            logger.info(f"Status check for subcategory: {subcategory}")
        
        # Get counts
        total_response = total_query.execute()
        processed_response = processed_query.execute()
        
        total = total_response.count if hasattr(total_response, 'count') else len(total_response.data)
        processed = processed_response.count if hasattr(processed_response, 'count') else len(processed_response.data)
        remaining = total - processed
        
        status_msg = f"📊 Processing Status"
        if subcategory:
            status_msg += f" ({subcategory})"
        status_msg += f": {processed}/{total} pages processed ({remaining} remaining)"
        logger.info(status_msg)
        
        if remaining > 0:
            # Estimate time
            pages_per_batch = 10
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
    
    # Configuration - Process all unprocessed pages
    TARGET_SUBCATEGORY = None  # Process all subcategories
    TARGET_DATASHEET_COUNT = None  # Process pages with any number of datasheets
    BATCH_SIZE = 10
    
    # Add timestamp separator
    logger.info("=" * 60)
    logger.info(f"Batch processing started at {datetime.now()}")
    if TARGET_SUBCATEGORY is None and TARGET_DATASHEET_COUNT == 0:
        logger.info("Target: All unprocessed pages WITHOUT datasheets (web content only)")
    elif TARGET_SUBCATEGORY is None:
        logger.info("Target: All unprocessed pages (any subcategory, any number of datasheets)")
    elif TARGET_DATASHEET_COUNT is None:
        logger.info(f"Target: {TARGET_SUBCATEGORY} (any number of datasheets)")
    else:
        logger.info(f"Target: {TARGET_SUBCATEGORY} with {TARGET_DATASHEET_COUNT} datasheet(s)")
    
    # Check status first
    asyncio.run(check_processing_status(subcategory=TARGET_SUBCATEGORY))
    
    # Process batch with filters
    results = asyncio.run(process_batch(
        subcategory=TARGET_SUBCATEGORY,
        datasheet_count=TARGET_DATASHEET_COUNT,
        batch_size=BATCH_SIZE
    ))
    
    logger.info(f"Batch processing ended at {datetime.now()}")
    logger.info("=" * 60)