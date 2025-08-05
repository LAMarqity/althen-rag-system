#!/usr/bin/env python3
"""
Debug script to verify page counting logic for miniature-force-sensors
This script will help identify the discrepancy between expected (39) and actual (40) counts
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

async def debug_page_counts():
    """Debug the exact counting logic used by batch_process_pages.py"""
    print("DEBUG: Debugging page count discrepancy for miniature-force-sensors")
    print("=" * 70)
    
    try:
        supabase = get_supabase_client()
        
        # 1. Check total pages in subcategory
        print("1. Total pages in miniature-force-sensors subcategory:")
        total_query = supabase.table("new_pages_index")\
            .select("id", count="exact")\
            .eq("subcategory", "miniature-force-sensors")
        total_response = total_query.execute()
        total_count = total_response.count if hasattr(total_response, 'count') else len(total_response.data)
        print(f"   Total: {total_count}")
        
        # 2. Check processed pages (rag_ingested = true)
        print("\n2. Processed pages (rag_ingested = true):")
        processed_query = supabase.table("new_pages_index")\
            .select("id", count="exact")\
            .eq("subcategory", "miniature-force-sensors")\
            .eq("rag_ingested", True)
        processed_response = processed_query.execute()
        processed_count = processed_response.count if hasattr(processed_response, 'count') else len(processed_response.data)
        print(f"   Processed: {processed_count}")
        
        # 3. Check unprocessed pages (rag_ingested = false OR null)
        print("\n3. Unprocessed pages (rag_ingested = false OR null):")
        unprocessed_query = supabase.table("new_pages_index")\
            .select("id", count="exact")\
            .eq("subcategory", "miniature-force-sensors")\
            .or_("rag_ingested.eq.false,rag_ingested.is.null")
        unprocessed_response = unprocessed_query.execute()
        unprocessed_count = unprocessed_response.count if hasattr(unprocessed_response, 'count') else len(unprocessed_response.data)
        print(f"   Unprocessed: {unprocessed_count}")
        
        # 4. Verify math
        print(f"\n4. Math check:")
        print(f"   Total: {total_count}")
        print(f"   Processed: {processed_count}")
        print(f"   Calculated remaining: {total_count - processed_count}")
        print(f"   Queried unprocessed: {unprocessed_count}")
        print(f"   Math correct: {total_count - processed_count == unprocessed_count}")
        
        # 5. Now check which of those unprocessed pages have exactly 1 datasheet
        print(f"\n5. Filtering unprocessed pages by datasheet count...")
        
        # Get all unprocessed pages to filter by datasheet count
        all_unprocessed_query = supabase.table("new_pages_index")\
            .select("*")\
            .eq("subcategory", "miniature-force-sensors")\
            .or_("rag_ingested.eq.false,rag_ingested.is.null")\
            .limit(100)  # Get all to filter manually
        all_unprocessed_response = all_unprocessed_query.execute()
        all_unprocessed_pages = all_unprocessed_response.data if all_unprocessed_response.data else []
        
        print(f"   Retrieved {len(all_unprocessed_pages)} unprocessed pages for filtering")
        
        # Count datasheets for each page
        pages_with_1_datasheet = []
        pages_with_0_datasheets = []
        pages_with_multiple_datasheets = []
        
        for page in all_unprocessed_pages:
            # Count datasheets for this page
            datasheet_response = supabase.table("new_datasheets_index")\
                .select("id", count="exact")\
                .eq("parent_url", page['url'])\
                .execute()
            
            datasheet_count = len(datasheet_response.data) if datasheet_response.data else 0
            
            if datasheet_count == 0:
                pages_with_0_datasheets.append(page)
            elif datasheet_count == 1:
                pages_with_1_datasheet.append(page)
            else:
                pages_with_multiple_datasheets.append(page)
        
        print(f"\n6. Datasheet count breakdown:")
        print(f"   Pages with 0 datasheets: {len(pages_with_0_datasheets)}")
        print(f"   Pages with 1 datasheet: {len(pages_with_1_datasheet)}")
        print(f"   Pages with 2+ datasheets: {len(pages_with_multiple_datasheets)}")
        print(f"   Total: {len(pages_with_0_datasheets) + len(pages_with_1_datasheet) + len(pages_with_multiple_datasheets)}")
        
        # 7. Show expected vs actual
        print(f"\n7. Expected vs Actual:")
        print(f"   User expected: 39 pages with 1 datasheet")
        print(f"   Batch script showed: 40 remaining out of 42 total (2 processed)")
        print(f"   Our count: {len(pages_with_1_datasheet)} pages with exactly 1 datasheet")
        print(f"   Discrepancy: {len(pages_with_1_datasheet) - 39}")
        
        # 8. If there's a discrepancy, show some examples
        if len(pages_with_1_datasheet) != 39:
            print(f"\n8. Sample pages with 1 datasheet (showing first 5):")
            for i, page in enumerate(pages_with_1_datasheet[:5]):
                print(f"   {i+1}. ID: {page['id']}, URL: {page['url'][:60]}...")
                print(f"      rag_ingested: {page.get('rag_ingested')}")
        
        # 9. Check if any pages have inconsistent rag_ingested values
        print(f"\n9. Checking for any data inconsistencies...")
        
        # Check pages with rag_ingested = true but also matching our unprocessed filter
        inconsistent_query = supabase.table("new_pages_index")\
            .select("*")\
            .eq("subcategory", "miniature-force-sensors")\
            .eq("rag_ingested", True)\
            .or_("rag_ingested.eq.false,rag_ingested.is.null")
        inconsistent_response = inconsistent_query.execute()
        inconsistent_pages = inconsistent_response.data if inconsistent_response.data else []
        
        if inconsistent_pages:
            print(f"   WARNING: Found {len(inconsistent_pages)} pages with inconsistent rag_ingested values")
            for page in inconsistent_pages[:3]:
                print(f"   - ID: {page['id']}, rag_ingested: {page.get('rag_ingested')}")
        else:
            print(f"   OK: No data inconsistencies found")
            
    except Exception as e:
        print(f"ERROR: Error during debug: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_page_counts())