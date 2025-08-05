#!/usr/bin/env python3
"""
Analyze the exact batch processing logic to understand the discrepancy
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

from scripts.raganything_api_service import get_supabase_client

async def analyze_batch_logic():
    """Reproduce the exact logic from get_unprocessed_pages function"""
    print("ANALYSIS: Reproducing batch_process_pages.py logic")
    print("=" * 60)
    
    try:
        supabase = get_supabase_client()
        
        # Step 1: Reproduce the exact query from get_unprocessed_pages
        print("1. Reproducing get_unprocessed_pages logic:")
        
        subcategory = "miniature-force-sensors"
        datasheet_count = 1
        limit = 50  # Get more than we need to filter
        
        # Build query for unprocessed pages (exact copy from batch script)
        query = supabase.table("new_pages_index")\
            .select("*")\
            .or_("rag_ingested.eq.false,rag_ingested.is.null")
        
        # Add subcategory filter
        query = query.eq("subcategory", subcategory)
        print(f"   Filtering for subcategory: {subcategory}")
        
        # Get pages (exact copy: limit * 3)
        response = query.limit(limit * 3).execute()
        pages = response.data if response.data else []
        print(f"   Retrieved {len(pages)} pages from initial query")
        
        # Step 2: Filter by datasheet count (exact copy from batch script)
        print("\n2. Filtering by datasheet count:")
        filtered_pages = []
        for i, page in enumerate(pages):
            print(f"   Processing page {i+1}/{len(pages)}: ID {page['id']}")
            
            # Count datasheets for this page (exact copy)
            datasheet_response = supabase.table("new_datasheets_index")\
                .select("id", count="exact")\
                .eq("parent_url", page['url'])\
                .execute()
            
            actual_count = len(datasheet_response.data) if datasheet_response.data else 0
            
            # Apply datasheet count filter (exact copy)
            if datasheet_count is not None:
                if actual_count == datasheet_count:
                    filtered_pages.append(page)
                    print(f"      MATCH: Page {page['id']} has exactly {actual_count} datasheet(s)")
                else:
                    print(f"      SKIP: Page {page['id']} has {actual_count} datasheet(s), need {datasheet_count}")
            
            # Stop if we have enough pages (exact copy)
            if len(filtered_pages) >= limit:
                print(f"      LIMIT REACHED: {len(filtered_pages)} pages found")
                break
        
        print(f"\n3. Final results:")
        print(f"   Total pages retrieved: {len(pages)}")
        print(f"   Pages matching criteria: {len(filtered_pages)}")
        print(f"   Batch script would process: {min(3, len(filtered_pages))} pages")
        
        # Step 3: Compare with user expectation
        print(f"\n4. User expectation analysis:")
        print(f"   User expected: 39 pages with 1 datasheet")
        print(f"   Batch found: {len(filtered_pages)} pages with 1 datasheet")
        print(f"   Our debug found: 36 pages with 1 datasheet")
        
        if len(filtered_pages) != 36:
            print(f"   DISCREPANCY: Batch logic found {len(filtered_pages)}, debug found 36")
            print(f"   This suggests an issue with the filtering logic")
        else:
            print(f"   CONSISTENT: Both methods found the same count")
        
        # Step 4: Check if the discrepancy is due to recent processing
        print(f"\n5. Checking if recent processing explains the difference:")
        
        # Check when the last pages were processed
        recent_processed = supabase.table("new_pages_index")\
            .select("*")\
            .eq("subcategory", subcategory)\
            .eq("rag_ingested", True)\
            .order("rag_ingested_at", desc=True)\
            .limit(5)\
            .execute()
        
        if recent_processed.data:
            print(f"   Last {len(recent_processed.data)} processed pages:")
            for page in recent_processed.data:
                print(f"   - ID: {page['id']}, processed: {page.get('rag_ingested_at', 'unknown')}")
        else:
            print(f"   No recently processed pages found")
            
        # Step 5: Explanation of the discrepancy
        print(f"\n6. DISCREPANCY EXPLANATION:")
        print(f"   Original expectation: 39 pages")
        print(f"   Current reality: 36 pages with 1 datasheet + 2 with multiple datasheets")
        print(f"   Total unprocessed: 38 pages")
        print(f"   Already processed: 4 pages")
        print(f"   Total in subcategory: 42 pages")
        print(f"")
        print(f"   The user's expectation of 39 pages was likely based on:")
        print(f"   - An earlier count when fewer pages were processed")
        print(f"   - Or a count that included some pages with multiple datasheets")
        print(f"   - Or the count included different filtering criteria")
        
        # Step 6: Show current processing targets
        print(f"\n7. CURRENT PROCESSING TARGETS:")
        print(f"   Pages the batch script will process: {min(3, len(filtered_pages))}")
        if filtered_pages:
            for i, page in enumerate(filtered_pages[:3]):
                print(f"   {i+1}. ID: {page['id']}, URL: {page['url'][:50]}...")
                
    except Exception as e:
        print(f"ERROR: Error during analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(analyze_batch_logic())