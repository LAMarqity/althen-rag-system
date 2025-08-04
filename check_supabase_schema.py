#!/usr/bin/env python3
"""
Check actual Supabase table schema to understand available fields
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent / 'scripts'))

from raganything_api_service import get_supabase_client

load_dotenv()

def check_table_schema():
    """Check the actual structure of the new_pages_index table"""
    
    print("Checking Supabase table schema...")
    
    try:
        supabase = get_supabase_client()
        
        # Fetch a few sample records to see the actual fields
        print("\n1. Fetching sample records from new_pages_index...")
        response = supabase.table("new_pages_index").select("*").limit(3).execute()
        
        if response.data:
            sample_record = response.data[0]
            print(f"\nSample record fields:")
            for field, value in sample_record.items():
                field_type = type(value).__name__
                print(f"  {field}: {field_type} = {repr(value)}")
                
            print(f"\nAll available fields in new_pages_index:")
            fields = list(sample_record.keys())
            for field in sorted(fields):
                print(f"  - {field}")
                
            # Check for the specific fields requested
            requested_fields = ['url_lang', 'image_url', 'image_title', 'category', 'subcategory']
            print(f"\nChecking for requested fields:")
            for field in requested_fields:
                exists = field in sample_record
                status = "EXISTS" if exists else "NOT FOUND"
                print(f"  {field}: {status}")
                if exists:
                    print(f"    Value: {repr(sample_record[field])}")
                
        else:
            print("No records found in table")
            
        # Also check new_datasheets_index for comparison
        print(f"\n2. Checking new_datasheets_index structure...")
        response = supabase.table("new_datasheets_index").select("*").limit(1).execute()
        
        if response.data:
            sample_record = response.data[0]
            print(f"\nDatasheets table fields:")
            for field in sorted(sample_record.keys()):
                print(f"  - {field}")
        else:
            print("No datasheet records found")
            
    except Exception as e:
        print(f"Error checking schema: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_table_schema()