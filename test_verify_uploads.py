#!/usr/bin/env python3
"""
Verify uploaded content is searchable
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
    print("=== Verifying Uploaded Content ===\n")
    
    queries = [
        "What is the CP22-E potentiometer?",
        "What types of sensors does Althen offer?",
        "Tell me about Althen sensor categories",
        "What force sensors are available?"
    ]
    
    for query in queries:
        print(f"Q: {query}")
        answer = await query_lightrag(query)
        
        # Truncate long answers
        if isinstance(answer, str) and len(answer) > 300:
            answer = answer[:300] + "..."
        
        print(f"A: {answer}\n")

if __name__ == "__main__":
    asyncio.run(main())