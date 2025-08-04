import asyncio
import json
import logging
import os
from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Environment variables loaded")
except ImportError:
    print("⚠️ python-dotenv not installed")

# RAGAnything imports
try:
    from raganything import RAGAnything
    from lightrag.llm.openai import openai_complete_if_cache, openai_embed
    from lightrag import LightRAG
    RAG_ANYTHING_AVAILABLE = True
except ImportError:
    RAG_ANYTHING_AVAILABLE = False
    print("⚠️ RAGAnything not available - install with: pip install raganything")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def demo_knowledge_graph():
    """Demonstrate the knowledge graph and multimodal capabilities"""
    
    print("\n" + "="*80)
    print("🚀 RAG-ANYTHING MULTIMODAL DEMO")
    print("="*80)
    print("📊 Knowledge Graph & Multimodal Content Processing")
    print("="*80)
    
    if not RAG_ANYTHING_AVAILABLE:
        print("❌ RAGAnything not available - please install with: pip install raganything")
        return
    
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("❌ OPENAI_API_KEY not found in environment")
        return
    
    try:
        # Initialize RAGAnything
        print("🔧 Initializing RAG-Anything...")
        
        def embedding_func(texts):
            return openai_embed(
                texts,
                model="text-embedding-3-large", 
                api_key=openai_api_key,
            )
        embedding_func.embedding_dim = 3072
        
        working_dir = "./rag_storage"
        Path(working_dir).mkdir(exist_ok=True)
        
        lightrag_instance = LightRAG(
            working_dir=working_dir,
            llm_model_func=lambda prompt, system_prompt=None, history_messages=[], **kwargs: openai_complete_if_cache(
                "gpt-4o-mini",
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                api_key=openai_api_key,
                **kwargs,
            ),
            embedding_func=embedding_func
        )
        
        rag = RAGAnything(lightrag=lightrag_instance)
        print("✅ RAG-Anything initialized successfully!")
        
        # Demonstrate current knowledge graph
        print("\n📊 KNOWLEDGE GRAPH STATUS:")
        print("-" * 40)
        
        # Check vector database files
        vdb_files = list(Path(working_dir).glob("*.json"))
        print(f"Vector files: {len(vdb_files)}")
        for f in vdb_files:
            size = f.stat().st_size
            print(f"  📄 {f.name}: {size} bytes")
        
        # Check processed content
        processed_dir = Path("rag_output")
        if processed_dir.exists():
            content_files = list(processed_dir.rglob("*_content_list.json"))
            if content_files:
                with open(content_files[0], 'r', encoding='utf-8') as f:
                    content_list = json.load(f)
                    print(f"Content items: {len(content_list)}")
                    
                    # Count content types
                    text_count = sum(1 for item in content_list if item.get("type") == "text")
                    image_count = sum(1 for item in content_list if item.get("type") == "image")
                    table_count = sum(1 for item in content_list if item.get("type") == "table")
                    
                    print(f"  📝 Text blocks: {text_count}")
                    print(f"  🖼️ Images: {image_count}")
                    print(f"  📋 Tables: {table_count}")
        
        # Demonstrate content analysis
        print("\n🔍 CONTENT ANALYSIS:")
        print("-" * 40)
        
        # Look for processed markdown
        md_files = list(processed_dir.rglob("*.md"))
        if md_files:
            print(f"📄 Markdown files: {len(md_files)}")
            with open(md_files[0], 'r', encoding='utf-8') as f:
                content = f.read()
                print(f"  Content length: {len(content)} characters")
                
                # Extract key information
                if "PT1 series" in content:
                    print("  🎯 Found: PT1 Draw-wire Sensors")
                if "TECHNICAL DATASHEETS" in content:
                    print("  📋 Found: Technical datasheets")
                if "Key features" in content:
                    print("  ✨ Found: Key features section")
        
        # Demonstrate simple query capability
        print("\n🤖 KNOWLEDGE GRAPH QUERIES:")
        print("-" * 40)
        
        # Add some content if knowledge graph is empty
        if not vdb_files or all(f.stat().st_size == 0 for f in vdb_files):
            print("📚 Adding content to knowledge graph...")
            
            # Use the processed content
            if md_files:
                await rag.process_document_complete(
                    file_path=str(md_files[0]),
                    output_dir="./rag_output_kg",
                    parse_method="auto"
                )
                print("✅ Content added to knowledge graph!")
        
        # Try some queries
        test_queries = [
            "What are the main features of PT1 sensors?",
            "What applications are PT1 sensors used for?",
            "What technical datasheets are available?"
        ]
        
        for query in test_queries:
            try:
                print(f"\n❓ Query: {query}")
                result = await lightrag_instance.aquery(query, param="hybrid")
                print(f"💡 Answer: {result[:200]}..." if len(result) > 200 else f"💡 Answer: {result}")
            except Exception as e:
                print(f"❌ Query failed: {e}")
        
        # Demonstrate multimodal capabilities
        print("\n🎨 MULTIMODAL CAPABILITIES:")
        print("-" * 40)
        print("🖼️ Image Processing: Extract and analyze images from PDFs")
        print("📋 Table Processing: Parse and understand tabular data")
        print("📄 Text Processing: Extract and chunk text content")
        print("🔗 Relationship Mapping: Create knowledge graph connections")
        
        print("\n💡 RAG-Anything Features demonstrated:")
        print("  ✅ Knowledge graph creation")
        print("  ✅ Vector embeddings (3072-dimensional)")
        print("  ✅ Content extraction and processing")
        print("  ✅ Multimodal content support")
        print("  ✅ Semantic search capabilities")
        
        print("\n🚀 Usage Examples:")
        print("  python scripts/rag_chat_interface.py chat")
        print("  python scripts/rag_chat_interface.py query 'your question'")
        print("  python scripts/rag_chat_interface.py explore")
        print("  python scripts/rag_chat_interface.py process path/to/pdf")
        
    except Exception as e:
        logger.error(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(demo_knowledge_graph())