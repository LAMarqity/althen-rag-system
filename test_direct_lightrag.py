#!/usr/bin/env python3
"""
Test accessing LightRAG directly for querying
"""

import asyncio
import json
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

async def test_direct_lightrag():
    """Test LightRAG directly"""
    print("=== Testing Direct LightRAG Access ===")
    
    try:
        # Import LightRAG directly
        from lightrag import LightRAG, QueryParam
        from lightrag.llm.openai import openai_complete_if_cache, openai_embed
        from lightrag.utils import EmbeddingFunc
        
        print("1. Initializing LightRAG directly...")
        
        # API configuration
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        working_dir = os.getenv("WORKING_DIR", "./knowledge_base")
        
        # LLM model function
        def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
            return openai_complete_if_cache(
                "gpt-4o-mini",
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                api_key=api_key,
                base_url=base_url,
                **kwargs,
            )
        
        # Embedding function
        embedding_func = EmbeddingFunc(
            embedding_dim=3072,
            max_token_size=8192,
            func=lambda texts: openai_embed(
                texts,
                model="text-embedding-3-large",
                api_key=api_key,  
                base_url=base_url,
            ),
        )
        
        # Initialize LightRAG
        rag = LightRAG(
            working_dir=working_dir,
            llm_model_func=llm_model_func,
            embedding_func=embedding_func
        )
        
        print("   LightRAG initialized successfully")
        print(f"   Working directory: {working_dir}")
        
        # Test queries
        test_queries = [
            "What sensors are available for pressure measurement?",
            "Tell me about the KDJ-PA sensor specifications",
            "What are string potentiometers used for?"
        ]
        
        print("\n2. Testing queries...")
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n--- Query {i}: {query} ---")
            
            try:
                # Try simple query first
                print(f"\n  Simple query:")
                result = await rag.aquery(query)
                
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
                import traceback
                traceback.print_exc()
        
        print("\n3. Knowledge base file check:")
        
        # Check knowledge base files
        kb_files = [
            "vdb_entities.json",
            "vdb_relationships.json", 
            "vdb_chunks.json",
            "graph_chunk_entity_relation.graphml",
            "kv_store_full_docs.json"
        ]
        
        for file_name in kb_files:
            file_path = os.path.join(working_dir, file_name)
            if os.path.exists(file_path):
                size = os.path.getsize(file_path)
                print(f"   {file_name}: {size} bytes")
            else:
                print(f"   {file_name}: not found")
        
        print("\n4. Test completed!")
        
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_direct_lightrag())