#!/usr/bin/env python3
"""
Find pages that have associated PDFs for testing
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent / 'scripts'))

from raganything_api_service import get_supabase_client

load_dotenv()

def find_pages_with_pdfs():
    """Find pages that have associated datasheets"""
    
    try:
        supabase = get_supabase_client()
        
        print("Looking for pages with associated PDFs...")
        
        # Get datasheets and their parent pages
        response = supabase.table("new_datasheets_index").select("*").limit(10).execute()
        
        if response.data:
            print(f"\nFound {len(response.data)} datasheets:")
            
            parent_pages = set()
            for ds in response.data:
                parent_url = ds.get('parent_url', '')
                print(f"  Datasheet ID: {ds.get('id')}, Parent: {parent_url}")
                
                # Extract page ID from parent URL if possible
                if parent_url:
                    # Look for the page in new_pages_index
                    page_response = supabase.table("new_pages_index").select("id, url, business_area, category, subcategory").eq("url", parent_url).execute()
                    
                    if page_response.data:
                        page = page_response.data[0]
                        parent_pages.add(page['id'])
                        print(f"    -> Page ID: {page['id']}, Category: {page.get('category')}")
            
            print(f"\nPages with PDFs found:")
            for page_id in sorted(parent_pages):
                print(f"  Page ID: {page_id}")
                
            if parent_pages:
                test_page = min(parent_pages)
                print(f"\nSuggested test page: {test_page}")
                return test_page
        else:
            print("No datasheets found")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    return None

if __name__ == "__main__":
    find_pages_with_pdfs()