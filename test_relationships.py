#!/usr/bin/env python3
"""
Test relationship queries in LightRAG
"""

import asyncio
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()

async def query_lightrag(query: str):
    """Query the LightRAG server"""
    server_url = os.getenv("LIGHTRAG_SERVER_URL", "").rstrip('/')
    api_key = os.getenv("LIGHTRAG_API_KEY")
    
    try:
        async with aiohttp.ClientSession() as session:
            data = {"query": query, "mode": "hybrid"}
            headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
            
            async with session.post(f"{server_url}/query", json=data, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("answer", result.get("response", str(result)))
                else:
                    return f"Error: HTTP {response.status}"
    except Exception as e:
        return f"Error: {e}"

async def main():
    print("=== Testing Document Relationships ===\n")
    
    queries = [
        "What is the parent URL of the CP22-E datasheet?",
        "Tell me about page ID 9022 and its datasheets",
        "What technical specifications are in the CP22-E potentiometer datasheet?",
        "What is the PM8 purge module and its specifications?",
        "Show me the relationship between web pages and their datasheets"
    ]
    
    for query in queries:
        print(f"Q: {query}")
        answer = await query_lightrag(query)
        
        # Clean and truncate long answers
        if isinstance(answer, str):
            # Remove problematic Unicode characters
            answer = answer.encode('ascii', 'ignore').decode('ascii')
            if len(answer) > 400:
                answer = answer[:400] + "..."
        
        print(f"A: {answer}\n")

if __name__ == "__main__":
    asyncio.run(main())