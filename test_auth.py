#!/usr/bin/env python3
import asyncio
import aiohttp
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def test_auth_methods():
    server_url = os.getenv('LIGHTRAG_SERVER_URL', '').rstrip('/')
    api_key = os.getenv('LIGHTRAG_API_KEY')
    
    test_data = {
        'content': 'test content',
        'metadata': {'test': True}
    }
    
    auth_methods = [
        {'Authorization': f'Bearer {api_key}'},
        {'Authorization': f'ApiKey {api_key}'},
        {'X-API-Key': api_key},
        {'api_key': api_key},
    ]
    
    async with aiohttp.ClientSession() as session:
        for i, headers in enumerate(auth_methods):
            print(f'Testing auth method {i+1}: {list(headers.keys())[0]}')
            
            try:
                headers['Content-Type'] = 'application/json'
                
                async with session.post(f'{server_url}/documents/text', 
                                      json=test_data, 
                                      headers=headers, 
                                      timeout=aiohttp.ClientTimeout(total=10)) as response:
                    
                    print(f'  Status: {response.status}')
                    if response.status != 401:
                        text = await response.text()
                        print(f'  Response: {text[:200]}')
                        if response.status == 200:
                            print('  SUCCESS! This auth method works')
                            break
                    
            except Exception as e:
                print(f'  Error: {e}')

asyncio.run(test_auth_methods())