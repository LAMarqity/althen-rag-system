#!/usr/bin/env python3
"""
Batch process unprocessed pages with parallel execution support
Modified to handle concurrent runs without conflicts
"""
import os
import sys
import asyncio
import random
from pathlib import Path
from datetime import datetime
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.raganything_api_service import get_supabase_client, logger

# Worker ID from environment or random
WORKER_ID = os.getenv('WORKER_ID', str(random.randint(1, 999)))

async def get_unprocessed_pages(limit=10, subcategory=None, datasheet_count=None):
    """
    Get pages that haven't been processed yet with specific filters
    Modified to handle concurrent workers by using row-level locking
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
            logger.info(f"[Worker {WORKER_ID}] Filtering for subcategory: {subcategory}")
        
        # Get more pages than needed to handle concurrent workers
        response = query.limit(limit * 5).execute()
        pages = response.data if response.data else []
        
        # Shuffle to reduce conflicts between workers
        random.shuffle(pages)
        
        # Filter by datasheet count if specified
        filtered_pages = []
        for page in pages:
            # Skip if already being processed (check for lock)
            if page.get('processing_locked'):
                continue
                
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
                    logger.info(f"[Worker {WORKER_ID}] Page {page['id']} has {actual_count} datasheet(s)")
            else:
                filtered_pages.append(page)
                logger.info(f"[Worker {WORKER_ID}] Page {page['id']} has {actual_count} datasheet(s)")
            
            # Stop if we have enough pages
            if len(filtered_pages) >= limit:
                break
        
        logger.info(f"[Worker {WORKER_ID}] Found {len(filtered_pages)} pages matching criteria")
        return filtered_pages
        
    except Exception as e:
        logger.error(f"[Worker {WORKER_ID}] Error fetching unprocessed pages: {e}")
        return []

async def lock_page_for_processing(page_id):
    """Attempt to lock a page for processing to avoid conflicts"""
    try:
        supabase = get_supabase_client()
        
        # Try to lock the page (set processing_locked to true)
        response = supabase.table("new_pages_index")\
            .update({"processing_locked": True, "processing_worker": WORKER_ID})\
            .eq("id", page_id)\
            .or_("processing_locked.eq.false,processing_locked.is.null")\
            .execute()
        
        # Check if we successfully locked it
        if response.data and len(response.data) > 0:
            logger.info(f"[Worker {WORKER_ID}] Successfully locked page {page_id}")
            return True
        else:
            logger.info(f"[Worker {WORKER_ID}] Page {page_id} already locked by another worker")
            return False
            
    except Exception as e:
        logger.error(f"[Worker {WORKER_ID}] Error locking page {page_id}: {e}")
        return False

async def unlock_page(page_id):
    """Unlock a page after processing"""
    try:
        supabase = get_supabase_client()
        supabase.table("new_pages_index")\
            .update({"processing_locked": False, "processing_worker": None})\
            .eq("id", page_id)\
            .execute()
    except Exception as e:
        logger.error(f"[Worker {WORKER_ID}] Error unlocking page {page_id}: {e}")

async def process_batch(subcategory=None, datasheet_count=None, batch_size=10):
    """
    Process a batch of pages with parallel execution support
    """
    from scripts.process_enhance_alt_text import process_page_enhance_alt_text
    
    # Get unprocessed pages
    pages = await get_unprocessed_pages(
        limit=batch_size * 2,  # Get extra pages in case some are locked
        subcategory=subcategory,
        datasheet_count=datasheet_count
    )
    
    if not pages:
        logger.info(f"[Worker {WORKER_ID}] No unprocessed pages found")
        return {"processed": 0, "success": 0, "failed": 0, "skipped": 0}
    
    logger.info(f"[Worker {WORKER_ID}] Starting batch processing")
    
    results = {"processed": 0, "success": 0, "failed": 0, "skipped": 0}
    
    for page in pages:
        # Stop if we've processed enough
        if results["processed"] >= batch_size:
            break
            
        # Try to lock the page
        if not await lock_page_for_processing(page['id']):
            results["skipped"] += 1
            continue
        
        try:
            logger.info(f"[Worker {WORKER_ID}] Processing page {page['id']}: {page['url'][:50]}...")
            result = await process_page_enhance_alt_text(page['id'])
            
            results["processed"] += 1
            
            if result['success']:
                results["success"] += 1
                logger.info(f"[Worker {WORKER_ID}] ✅ Successfully processed page {page['id']}")
                logger.info(f"[Worker {WORKER_ID}]    - Content length: {result.get('content_length', 0):,} chars")
                logger.info(f"[Worker {WORKER_ID}]    - Images uploaded: {result.get('images_uploaded', 0)}")
                logger.info(f"[Worker {WORKER_ID}]    - Datasheets: {result.get('datasheets_processed', 0)}")
            else:
                results["failed"] += 1
                logger.error(f"[Worker {WORKER_ID}] ❌ Failed to process page {page['id']}: {result.get('error')}")
                
        except Exception as e:
            results["failed"] += 1
            logger.error(f"[Worker {WORKER_ID}] Error processing page {page['id']}: {e}")
        finally:
            # Always unlock the page
            await unlock_page(page['id'])
        
        # Small delay between pages
        await asyncio.sleep(1)
    
    logger.info(f"[Worker {WORKER_ID}] Batch complete: Processed {results['processed']}, Success {results['success']}, Failed {results['failed']}, Skipped {results['skipped']}")
    return results

async def check_processing_status(subcategory=None):
    """Check overall processing status"""
    try:
        supabase = get_supabase_client()
        
        # Build queries
        total_query = supabase.table("new_pages_index").select("id", count="exact")
        processed_query = supabase.table("new_pages_index").select("id", count="exact").eq("rag_ingested", True)
        
        if subcategory:
            total_query = total_query.eq("subcategory", subcategory)
            processed_query = processed_query.eq("subcategory", subcategory)
        
        # Get counts
        total_response = total_query.execute()
        processed_response = processed_query.execute()
        
        total = total_response.count if hasattr(total_response, 'count') else len(total_response.data)
        processed = processed_response.count if hasattr(processed_response, 'count') else len(processed_response.data)
        remaining = total - processed
        
        logger.info(f"[Worker {WORKER_ID}] 📊 Status: {processed}/{total} pages processed ({remaining} remaining)")
        
        return {"total": total, "processed": processed, "remaining": remaining}
        
    except Exception as e:
        logger.error(f"[Worker {WORKER_ID}] Error checking status: {e}")
        return {"total": 0, "processed": 0, "remaining": 0}

if __name__ == "__main__":
    # Get worker ID from environment or command line
    if len(sys.argv) > 1:
        WORKER_ID = sys.argv[1]
    
    # Configure logging
    log_file = f'/workspace/althen-rag-system/logs/batch_worker_{WORKER_ID}.log' if os.path.exists('/workspace') else f'logs/batch_worker_{WORKER_ID}.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format=f'%(asctime)s - [Worker {WORKER_ID}] - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, mode='a'),
            logging.StreamHandler()
        ]
    )
    
    # Configuration
    TARGET_SUBCATEGORY = None
    TARGET_DATASHEET_COUNT = None
    BATCH_SIZE = 10
    
    logger.info(f"[Worker {WORKER_ID}] " + "=" * 60)
    logger.info(f"[Worker {WORKER_ID}] Batch processing started at {datetime.now()}")
    
    # Check status
    asyncio.run(check_processing_status(subcategory=TARGET_SUBCATEGORY))
    
    # Process batch
    results = asyncio.run(process_batch(
        subcategory=TARGET_SUBCATEGORY,
        datasheet_count=TARGET_DATASHEET_COUNT,
        batch_size=BATCH_SIZE
    ))
    
    logger.info(f"[Worker {WORKER_ID}] Batch processing ended at {datetime.now()}")
    logger.info(f"[Worker {WORKER_ID}] " + "=" * 60)