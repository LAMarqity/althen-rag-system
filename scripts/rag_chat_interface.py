import asyncio
import json
import logging
import os
import base64
import tempfile
from datetime import datetime
from pathlib import Path
from supabase import create_client, Client
import requests
from bs4 import BeautifulSoup

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Environment variables loaded")
except ImportError:
    print("⚠️ python-dotenv not installed")
except Exception as e:
    print(f"❌ Error loading .env: {e}")

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

class RAGChatInterface:
    def __init__(self):
        # Supabase setup
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_ANON_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("❌ SUPABASE_URL and SUPABASE_ANON_KEY environment variables are required")
        
        self.supabase = create_client(self.supabase_url, self.supabase_key)
        
        # OpenAI setup for RAGAnything
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        
        # RAGAnything setup
        self.rag_anything = None
        self.working_dir = os.getenv("WORKING_DIR", "./rag_storage")
        Path(self.working_dir).mkdir(exist_ok=True)
        
        logger.info("✅ RAG Chat Interface initialized")
    
    def initialize_rag_anything(self):
        """Initialize RAGAnything with OpenAI functions"""
        if not RAG_ANYTHING_AVAILABLE:
            logger.error("❌ RAGAnything not installed")
            return False
            
        if not self.openai_api_key:
            logger.error("❌ OPENAI_API_KEY not found")
            return False
        
        try:
            # Create embedding function with embedding_dim attribute
            def embedding_func(texts):
                return openai_embed(
                    texts,
                    model="text-embedding-3-large", 
                    api_key=self.openai_api_key,
                )
            embedding_func.embedding_dim = 3072
            
            # First create LightRAG instance
            lightrag_instance = LightRAG(
                working_dir=self.working_dir,
                llm_model_func=lambda prompt, system_prompt=None, history_messages=[], **kwargs: openai_complete_if_cache(
                    "gpt-4o-mini",
                    prompt,
                    system_prompt=system_prompt,
                    history_messages=history_messages,
                    api_key=self.openai_api_key,
                    **kwargs,
                ),
                embedding_func=embedding_func
            )
            
            # Then create RAGAnything with LightRAG instance
            self.rag_anything = RAGAnything(lightrag=lightrag_instance)
            logger.info("✅ RAGAnything initialized")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize RAGAnything: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def query_knowledge_graph(self, question, mode="hybrid"):
        """Query the RAGAnything knowledge graph"""
        if not self.rag_anything:
            if not self.initialize_rag_anything():
                return "❌ Failed to initialize RAGAnything"
        
        try:
            logger.info(f"🔍 Querying: {question}")
            # Use the non-async query method for now
            result = await self.rag_anything.query_with_multimodal(question, mode=mode)
            return result
        except Exception as e:
            logger.error(f"❌ Error querying knowledge graph: {e}")
            # If async doesn't work, try the sync version
            try:
                # For compatibility, try to use the lightrag directly
                if hasattr(self.rag_anything, 'lightrag'):
                    from lightrag.utils import logger as lightrag_logger
                    lightrag_logger.setLevel(logging.WARNING)  # Reduce noise
                    result = await self.rag_anything.lightrag.aquery(question, param=mode)
                    return result
                else:
                    return f"Error: {str(e)}"
            except Exception as e2:
                return f"Error: {str(e2)}"
    
    def get_knowledge_graph_stats(self):
        """Get statistics about the knowledge graph"""
        try:
            stats = {}
            
            # Check for vector database files
            vdb_files = list(Path(self.working_dir).glob("*.json"))
            stats["vector_files"] = [str(f.name) for f in vdb_files]
            
            # Check processed content
            processed_dir = Path("rag_output")
            if processed_dir.exists():
                processed_files = list(processed_dir.rglob("*.json"))
                stats["processed_files"] = len(processed_files)
                
                # Get content statistics
                content_files = list(processed_dir.rglob("*_content_list.json"))
                if content_files:
                    with open(content_files[0], 'r', encoding='utf-8') as f:
                        content_list = json.load(f)
                        stats["content_items"] = len(content_list)
                        stats["content_types"] = list(set(item.get("type", "unknown") for item in content_list))
            
            return stats
        except Exception as e:
            logger.error(f"❌ Error getting stats: {e}")
            return {"error": str(e)}
    
    async def process_pdf_with_images_tables(self, pdf_path, output_dir="./rag_output"):
        """Process PDF with enhanced image and table extraction"""
        if not self.rag_anything:
            if not self.initialize_rag_anything():
                return None
        
        try:
            logger.info(f"📄 Processing PDF with multimodal extraction: {pdf_path}")
            
            # Process with RAGAnything using MinerU for enhanced extraction
            result = await self.rag_anything.process_document_complete(
                file_path=pdf_path,
                output_dir=output_dir,
                parse_method="auto",  # Auto mode for best image/table detection
                display_stats=True
            )
            
            logger.info("✅ PDF processed with multimodal extraction")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error processing PDF: {e}")
            return None
    
    def explore_extracted_content(self, content_dir):
        """Explore extracted images, tables, and content"""
        try:
            content_path = Path(content_dir)
            exploration = {
                "images": [],
                "tables": [],
                "text_blocks": [],
                "metadata": {}
            }
            
            # Look for content list
            content_list_files = list(content_path.rglob("*_content_list.json"))
            if content_list_files:
                with open(content_list_files[0], 'r', encoding='utf-8') as f:
                    content_list = json.load(f)
                    
                    for item in content_list:
                        if isinstance(item, dict):
                            content_type = item.get("type", "unknown")
                            if content_type == "image":
                                exploration["images"].append(item)
                            elif content_type == "table":
                                exploration["tables"].append(item)
                            elif content_type == "text":
                                exploration["text_blocks"].append(item)
            
            # Look for extracted images
            images_dir = content_path / "auto" / "images"
            if images_dir.exists():
                image_files = list(images_dir.glob("*"))
                exploration["extracted_image_files"] = [str(f.name) for f in image_files]
            
            # Look for model data
            model_files = list(content_path.rglob("*_model.json"))
            if model_files:
                try:
                    with open(model_files[0], 'r', encoding='utf-8') as f:
                        model_data = json.load(f)
                        if isinstance(model_data, dict):
                            exploration["metadata"]["pages"] = len(model_data.get("pages", []))
                            exploration["metadata"]["elements"] = sum(len(page.get("blocks", [])) if isinstance(page, dict) else 0 for page in model_data.get("pages", []))
                except Exception as e:
                    exploration["metadata"]["model_error"] = str(e)
            
            return exploration
            
        except Exception as e:
            logger.error(f"❌ Error exploring content: {e}")
            return {"error": str(e)}
    
    async def interactive_chat(self):
        """Interactive chat session with the knowledge graph"""
        print("\n" + "="*60)
        print("🤖 RAG CHAT INTERFACE")
        print("="*60)
        print("💡 Ask questions about the ingested knowledge!")
        print("🔍 Available modes: hybrid, local, global")
        print("📊 Type 'stats' to see knowledge graph statistics")
        print("🗺️  Type 'explore' to explore extracted content")  
        print("❌ Type 'exit' to quit")
        print("="*60)
        
        if not self.initialize_rag_anything():
            print("❌ Failed to initialize RAGAnything")
            return
        
        while True:
            try:
                question = input("\n🔤 Your question: ").strip()
                
                if question.lower() == 'exit':
                    print("👋 Goodbye!")
                    break
                    
                elif question.lower() == 'stats':
                    stats = self.get_knowledge_graph_stats()
                    print("\n📊 KNOWLEDGE GRAPH STATISTICS:")
                    print(json.dumps(stats, indent=2))
                    continue
                    
                elif question.lower() == 'explore':
                    exploration = self.explore_extracted_content("./rag_output")
                    print("\n🗺️ EXTRACTED CONTENT EXPLORATION:")
                    print(f"📷 Images found: {len(exploration.get('images', []))}")
                    print(f"📋 Tables found: {len(exploration.get('tables', []))}")
                    print(f"📝 Text blocks: {len(exploration.get('text_blocks', []))}")
                    if exploration.get('extracted_image_files'):
                        print(f"🖼️ Image files: {exploration['extracted_image_files']}")
                    print(f"📄 Metadata: {exploration.get('metadata', {})}")
                    continue
                
                elif not question:
                    continue
                
                # Parse mode if specified
                mode = "hybrid"
                if question.startswith("["):
                    parts = question.split("]", 1)
                    if len(parts) == 2:
                        mode = parts[0][1:].strip()
                        question = parts[1].strip()
                
                print(f"\n🔍 Searching knowledge graph (mode: {mode})...")
                
                # Query the knowledge graph
                answer = await self.query_knowledge_graph(question, mode=mode)
                
                print(f"\n🤖 ANSWER:")
                print("-" * 40)
                print(answer)
                print("-" * 40)
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="RAG Chat Interface with Multimodal Support")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Commands
    chat_cmd = subparsers.add_parser('chat', help='Start interactive chat with knowledge graph')
    
    query_cmd = subparsers.add_parser('query', help='Ask a single question')
    query_cmd.add_argument('question', help='Question to ask')
    query_cmd.add_argument('--mode', default='hybrid', choices=['hybrid', 'local', 'global'], help='Query mode')
    
    stats_cmd = subparsers.add_parser('stats', help='Show knowledge graph statistics')
    
    explore_cmd = subparsers.add_parser('explore', help='Explore extracted content')
    explore_cmd.add_argument('--dir', default='./rag_output', help='Content directory to explore')
    
    process_cmd = subparsers.add_parser('process', help='Process a PDF with image/table extraction')
    process_cmd.add_argument('pdf_path', help='Path to PDF file')
    process_cmd.add_argument('--output', default='./rag_output', help='Output directory')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    try:
        interface = RAGChatInterface()
        
        if args.command == 'chat':
            await interface.interactive_chat()
            
        elif args.command == 'query':
            result = await interface.query_knowledge_graph(args.question, args.mode)
            print(f"Query: {args.question}")
            print(f"Mode: {args.mode}")
            print(f"Answer: {result}")
            
        elif args.command == 'stats':
            stats = interface.get_knowledge_graph_stats()
            print("📊 KNOWLEDGE GRAPH STATISTICS:")
            print(json.dumps(stats, indent=2))
            
        elif args.command == 'explore':
            exploration = interface.explore_extracted_content(args.dir)
            print("🗺️ EXTRACTED CONTENT EXPLORATION:")
            print(json.dumps(exploration, indent=2))
            
        elif args.command == 'process':
            result = await interface.process_pdf_with_images_tables(args.pdf_path, args.output)
            if result:
                print(f"✅ Successfully processed {args.pdf_path}")
                print(f"📁 Output directory: {args.output}")
            else:
                print(f"❌ Failed to process {args.pdf_path}")
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(asyncio.run(main()))