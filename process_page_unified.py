#!/usr/bin/env python3
"""
Unified page processor with correct field handling
Usage: python process_page_unified.py <page_id> [--rag] [--combine]

--rag: Use advanced RAG fields (rag_ingested, processing_metadata)
--combine: Combine web + PDF content into single document
"""

import os
import sys
import asyncio
import json
from datetime import datetime
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent / 'scripts'))

# Import the enhanced processor
from process_page_enhanced import EnhancedPageProcessor
from raganything_api_service import get_supabase_client

async def update_processing_status(page_id: int, datasheets_processed: list, 
                                  use_rag_fields: bool = False, 
                                  processing_results: dict = None):
    """Update Supabase with correct fields based on mode"""
    
    supabase = get_supabase_client()
    
    # Update pages table - ALWAYS set rag_ingested=true for consistency
    update_data = {
        "ingested": True,  # Always set for compatibility
        "rag_ingested": True,  # Always set for consistency
        "rag_ingested_at": datetime.now().isoformat(),  # Always timestamp
    }
    
    if use_rag_fields and processing_results:
        # Add detailed metadata only in RAG mode
        update_data["processing_metadata"] = json.dumps(processing_results)
        print("   Updating with full RAG fields + metadata...")
    else:
        # Still set RAG flags but without metadata
        print("   Updating with RAG flags (no metadata)...")
    
    supabase.table("new_pages_index").update(update_data).eq("id", page_id).execute()
    
    # Update datasheets table (only has ingested field)
    for datasheet_id in datasheets_processed:
        supabase.table("new_datasheets_index").update({
            "ingested": True
        }).eq("id", datasheet_id).execute()
    
    print(f"   [OK] Updated page {page_id} and {len(datasheets_processed)} datasheets")

async def main():
    """Main entry point with field handling options"""
    
    # Parse arguments
    if len(sys.argv) < 2:
        print("Usage: python process_page_unified.py <page_id> [options]")
        print("\nOptions:")
        print("  --rag     : Use advanced RAG fields (rag_ingested, metadata)")
        print("  --combine : Combine web + PDF content into single document")
        print("\nExamples:")
        print("  python process_page_unified.py 9022          # Simple processing")
        print("  python process_page_unified.py 9022 --rag    # With RAG tracking")
        print("  python process_page_unified.py 9022 --rag --combine")
        sys.exit(1)
    
    try:
        page_id = int(sys.argv[1])
    except ValueError:
        print(f"Error: Invalid page ID '{sys.argv[1]}' - must be a number")
        sys.exit(1)
    
    # Check flags
    use_rag_fields = "--rag" in sys.argv
    combine_content = "--combine" in sys.argv
    
    print(f"\n{'='*60}")
    print(f"Unified Page Processor")
    print(f"{'='*60}")
    print(f"Page ID: {page_id}")
    print(f"Field Mode: {'RAG (advanced)' if use_rag_fields else 'Simple'}")
    print(f"Content Mode: {'Combined' if combine_content else 'Separate'}")
    print(f"{'='*60}")
    
    # Process the page using enhanced processor
    processor = EnhancedPageProcessor(combine_content=combine_content)
    
    # Override the process_page method to handle field updates correctly
    original_process = processor.process_page
    
    async def process_with_correct_fields(page_id):
        # Get original results but don't update Supabase yet
        results = await original_process(page_id)
        
        # Extract processed datasheet IDs
        datasheets_processed = []
        for upload in results.get("uploads", []):
            if upload.get("type") == "pdf" and upload.get("id"):
                datasheets_processed.append(upload["id"])
        
        # Update with correct fields based on mode
        if results.get("status") == "success":
            # Prepare processing metadata for RAG mode
            processing_metadata = None
            if use_rag_fields:
                processing_metadata = {
                    "timestamp": datetime.now().isoformat(),
                    "uploads": results.get("uploads", []),
                    "pdf_count": results.get("pdf_count", 0),
                    "web_content": results.get("web_content", False),
                    "mode": results.get("mode", "unknown"),
                    "status": results.get("status", "unknown")
                }
            
            # Update Supabase with correct fields
            await update_processing_status(
                page_id, 
                datasheets_processed,
                use_rag_fields=use_rag_fields,
                processing_results=processing_metadata
            )
        
        return results
    
    # Replace the method temporarily
    processor.process_page = process_with_correct_fields
    
    # Process the page
    results = await processor.process_page(page_id)
    
    # Summary with field info
    print(f"\n{'='*60}")
    print("PROCESSING COMPLETE")
    print(f"{'='*60}")
    print(f"Status: {results.get('status')}")
    print(f"Fields Updated (always consistent):")
    print(f"  - ingested: true")
    print(f"  - rag_ingested: true")
    print(f"  - rag_ingested_at: {datetime.now().isoformat()}")
    if use_rag_fields:
        print(f"  - processing_metadata: JSON object (detailed)")
    else:
        print(f"  - processing_metadata: not set (simple mode)")
    print(f"{'='*60}\n")
    
    # Exit with appropriate code
    if results["status"] == "success":
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())