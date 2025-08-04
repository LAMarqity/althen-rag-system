#!/usr/bin/env python3
"""
Test querying the RAGAnything knowledge base
"""

import asyncio
import json
from dotenv import load_dotenv
from scripts.raganything_api_service import initialize_rag

# Load environment
load_dotenv()

async def test_knowledge_base_queries():
    """Test various queries against the processed knowledge base"""
    print("=== Testing Knowledge Base Queries ===")
    
    try:
        print("1. Initializing RAGAnything...")
        rag = await initialize_rag()
        print("   RAGAnything initialized successfully")
        
        # Test queries
        test_queries = [
            "What sensors are available for pressure measurement?",
            "Tell me about soil pressure sensors",
            "What are the specifications of the KDJ-PA sensor?",
            "What types of force sensors does Althen offer?",
            "Show me information about string potentiometers"
        ]
        
        print("\n2. Testing queries...")
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n--- Query {i}: {query} ---")
            
            try:
                # Test different query modes
                modes = ["hybrid", "local", "global", "naive"]
                
                for mode in modes:
                    print(f"\n  Mode: {mode}")
                    result = await rag.aquery(query, mode=mode)
                    
                    if result:
                        # Truncate long responses for readability
                        response_text = str(result)[:500]
                        if len(str(result)) > 500:
                            response_text += "..."
                        
                        print(f"    Response: {response_text}")
                    else:
                        print(f"    No results found")
                        
            except Exception as e:
                print(f"    Error: {e}")
        
        print("\n3. Knowledge base statistics:")
        
        # Try to get some stats about the knowledge base
        try:
            # Check if we can access the vector databases
            import os
            kb_files = [
                "knowledge_base/vdb_entities.json",
                "knowledge_base/vdb_relationships.json", 
                "knowledge_base/vdb_chunks.json"
            ]
            
            for file_path in kb_files:
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if isinstance(data, dict) and 'data' in data:
                                count = len(data['data'])
                                print(f"   {os.path.basename(file_path)}: {count} items")
                            else:
                                print(f"   {os.path.basename(file_path)}: exists")
                    except:
                        print(f"   {os.path.basename(file_path)}: exists (binary)")
                else:
                    print(f"   {os.path.basename(file_path)}: not found")
                    
        except Exception as e:
            print(f"   Error getting stats: {e}")
        
        print("\n4. Test completed!")
        
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_knowledge_base_queries())