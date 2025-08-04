#!/usr/bin/env python3
"""
Test simple upload to LightRAG server
"""

import asyncio
import aiohttp
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

async def test_simple_upload():
    """Test with minimal content"""
    server_url = os.getenv("LIGHTRAG_SERVER_URL", "").rstrip('/')
    api_key = os.getenv("LIGHTRAG_API_KEY")
    
    print("=== Testing Simple LightRAG Upload ===")
    print(f"Server: {server_url}")
    print(f"API Key: {api_key[:20]}...")
    
    # Very simple test content
    simple_content = f"CP22-E single turn potentiometer from Althen Controls. Test upload at {datetime.now().isoformat()}"
    
    data = {
        "text": simple_content,
        "file_source": "test_upload"
    }
    
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{server_url}/documents/text"
            print(f"\nUploading to: {url}")
            print(f"Content length: {len(simple_content)} characters")
            
            async with session.post(url, json=data, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                print(f"Response status: {response.status}")
                
                response_text = await response.text()
                print(f"Response: {response_text[:500]}")
                
                if response.status == 200:
                    print("\n✅ SUCCESS! Upload worked!")
                    result = await response.json() if response_text else {}
                    print(f"Result: {result}")
                else:
                    print(f"\n❌ Failed with status {response.status}")
                    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_simple_upload())