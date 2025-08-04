#!/usr/bin/env python3
"""
Test script for RAGAnything API processing locally
"""

import os
import asyncio
import json
from datetime import datetime
from dotenv import load_dotenv
from scripts.raganything_api_service import (
    initialize_rag, 
    fetch_page_data, 
    fetch_datasheets,
    process_page_background,
    get_supabase_client
)

# Load environment
load_dotenv()

async def test_single_page_processing():
    """Test processing a single page with PDF datasheets"""
    print("=== RAGAnything Local Test ===")
    
    # Test page with PDF datasheets (from our earlier search)
    test_page_id = 7289  # KDJ-PA/KDK-PA Load Cell Type Soil Pressure Gauge
    
    try:
        print(f"1. Testing page {test_page_id}")
        
        # Fetch page data
        page_data = await fetch_page_data(test_page_id)
        print(f"   Page URL: {page_data.get('url')}")
        print(f"   Business Area: {page_data.get('business_area')}")
        
        # Fetch datasheets
        datasheets = await fetch_datasheets(test_page_id)
        print(f"   Found {len(datasheets)} datasheets")
        
        for i, ds in enumerate(datasheets):
            print(f"     {i+1}. ID: {ds.get('id')}, URL: {ds.get('url')}")
        
        if not datasheets:
            print("   No datasheets found - cannot test PDF processing")
            return
        
        print("\n2. Initializing RAGAnything...")
        rag = await initialize_rag()
        print("   RAGAnything initialized successfully")
        
        print("\n3. Starting background processing...")
        job_id = f"test-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Initialize processing job properly
        from scripts.raganything_api_service import processing_jobs
        processing_jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0.0,
            "message": "Job queued for processing",
            "created_at": datetime.now(),
            "completed_at": None,
            "result": None,
            "error": None
        }
        
        # Run the background processing
        await process_page_background(
            job_id=job_id,
            page_id=test_page_id,
            process_datasheets=True,
            store_in_supabase=False  # Don't store in Supabase for local test
        )
        
        # Get results
        if job_id in processing_jobs:
            result = processing_jobs[job_id]
            print(f"\n4. Processing Results:")
            print(f"   Status: {result.get('status')}")
            print(f"   Message: {result.get('message')}")
            
            if result.get('result'):
                processed_docs = result['result'].get('processed_documents', [])
                print(f"   Processed documents: {len(processed_docs)}")
                
                for doc in processed_docs:
                    print(f"     - Datasheet ID: {doc.get('datasheet_id')}")
                    print(f"       PDF URL: {doc.get('pdf_url')}")
                    if doc.get('error'):
                        print(f"       Error: {doc.get('error')}")
                    elif doc.get('result'):
                        print(f"       Successfully processed with RAGAnything")
        
        print("\n5. Test completed!")
        
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Import processing_jobs globally for the test
    from scripts.raganything_api_service import processing_jobs
    
    asyncio.run(test_single_page_processing())