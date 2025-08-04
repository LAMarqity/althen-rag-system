#!/usr/bin/env python3
"""
Test querying the LightRAG server
"""

import asyncio
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()

async def query_lightrag_server(query: str, mode: str = "hybrid"):
    """Query the LightRAG server"""
    server_url = os.getenv("LIGHTRAG_SERVER_URL", "").rstrip('/')
    api_key = os.getenv("LIGHTRAG_API_KEY")
    
    try:
        async with aiohttp.ClientSession() as session:
            data = {
                "query": query,
                "mode": mode
            }
            
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            
            url = f"{server_url}/query"
            
            async with session.post(url, json=data, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"success": True, "response": result}
                else:
                    error_text = await response.text()
                    return {"error": f"HTTP {response.status}: {error_text}"}
                    
    except Exception as e:
        return {"error": str(e)}

async def test_queries():
    """Test various queries against the LightRAG server"""
    print("=== Testing LightRAG Server Queries ===\n")
    
    test_queries = [
        "What is the CP22-E single turn potentiometer?",
        "Tell me about Althen sensors",
        "What sensor datasheets are available?",
        "single turn potentiometer specifications"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"{i}. Query: {query}")
        result = await query_lightrag_server(query)
        
        if result.get("success"):
            response = result.get("response", {})
            
            # Handle different response formats
            if isinstance(response, dict):
                answer = response.get("answer", response.get("response", str(response)))
            else:
                answer = str(response)
            
            # Truncate long responses
            if len(answer) > 500:
                answer = answer[:500] + "..."
            
            print(f"   Response: {answer}")
        else:
            print(f"   Error: {result.get('error')}")
        
        print()
    
    print("Test completed!")

if __name__ == "__main__":
    asyncio.run(test_queries())