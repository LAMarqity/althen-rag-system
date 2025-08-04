#!/usr/bin/env python3
"""
Test client for RAG API Service
Demonstrates how to call the API from CRON jobs or other applications
"""

import requests
import time
import json
from typing import Dict, Any, List

class RAGAPIClient:
    """Client for calling the RAG API Service"""
    
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Check API service health"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": str(e), "status": "unreachable"}
    
    def process_page(self, page_id: int, fast_mode: bool = True, force_reprocess: bool = False) -> Dict[str, Any]:
        """Process a specific page"""
        try:
            data = {
                "page_id": page_id,
                "fast_mode": fast_mode,
                "force_reprocess": force_reprocess
            }
            
            response = requests.post(
                f"{self.api_url}/process-page",
                headers=self.headers,
                json=data,
                timeout=300  # 5 minutes
            )
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            return {"error": str(e), "success": False, "page_id": page_id}
    
    def get_page_status(self, page_id: int) -> Dict[str, Any]:
        """Get processing status for a page"""
        try:
            response = requests.get(
                f"{self.api_url}/status/{page_id}",
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            return {"error": str(e), "page_id": page_id}
    
    def batch_process(self, page_ids: List[int], fast_mode: bool = True) -> Dict[str, Any]:
        """Process multiple pages in batch"""
        try:
            response = requests.post(
                f"{self.api_url}/batch-process",
                headers=self.headers,
                json=page_ids,
                params={"fast_mode": fast_mode},
                timeout=600  # 10 minutes
            )
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            return {"error": str(e), "page_ids": page_ids}

def main():
    """Test the API client"""
    
    # Configuration - update these for your setup
    API_URL = "http://localhost:8080"
    API_KEY = "your-secure-api-key-here"  # Change this!
    
    print("[TEST] RAG API Client Test")
    print("=" * 40)
    
    # Initialize client
    client = RAGAPIClient(API_URL, API_KEY)
    
    # 1. Health Check
    print("1. Checking API health...")
    health = client.health_check()
    print(f"   Status: {health.get('status', 'unknown')}")
    if 'error' in health:
        print(f"   [ERROR] Error: {health['error']}")
        print("\n[INFO] Make sure the API service is running:")
        print("   python scripts/start_api.py")
        return
    else:
        print(f"   [OK] LightRAG Connected: {health.get('lightrag_connected', False)}")
    
    # 2. Check Page Status
    print("\n2. Checking page status...")
    test_page_id = 9066
    status = client.get_page_status(test_page_id)
    if 'error' in status:
        print(f"   [ERROR] Error: {status['error']}")
    else:
        print(f"   Page {test_page_id}: {status.get('status', 'unknown')}")
    
    # 3. Process Single Page (optional - commented out for safety)
    print("\n3. Page processing test...")
    print("   [WARNING] Uncomment the code below to test actual page processing")
    print(f"   This would process page {test_page_id}")
    
    # Uncomment to test actual processing:
    # print(f"   Processing page {test_page_id}...")
    # result = client.process_page(test_page_id, fast_mode=True)
    # if result.get('success'):
    #     print(f"   [OK] Success! Processing time: {result.get('processing_time', 'N/A')}s")
    # else:
    #     print(f"   [ERROR] Failed: {result.get('error', result.get('message', 'Unknown error'))}")
    
    print("\n[COMPLETE] API client test completed!")
    print("\n[NEXT] Next steps:")
    print("   - Update API_URL and API_KEY in this script")
    print("   - Uncomment the processing test above")
    print("   - Use this client in your CRON jobs")

def cron_job_example():
    """Example CRON job function"""
    
    # Configuration from environment or config file
    import os
    API_URL = os.getenv("RAG_API_URL", "http://localhost:8080")
    API_KEY = os.getenv("RAG_API_KEY", "your-api-key")
    
    client = RAGAPIClient(API_URL, API_KEY)
    
    # Pages to process (get from database, config, etc.)
    pages_to_process = [9066, 9067, 9074]
    
    print(f"[CRON] CRON Job: Processing {len(pages_to_process)} pages")
    
    for page_id in pages_to_process:
        print(f"Processing page {page_id}...")
        
        # Check if already processed
        status = client.get_page_status(page_id)
        if status.get('status') == 'ingested':
            print(f"   [SKIP] Page {page_id} already ingested, skipping")
            continue
        
        # Process the page
        result = client.process_page(page_id, fast_mode=True)
        
        if result.get('success'):
            print(f"   [OK] Page {page_id} processed successfully")
        else:
            print(f"   [ERROR] Page {page_id} failed: {result.get('error', 'Unknown error')}")
        
        # Small delay between pages
        time.sleep(5)
    
    print("[COMPLETE] CRON job completed!")

if __name__ == "__main__":
    main()
    
    # Example: Run CRON job function
    # cron_job_example()