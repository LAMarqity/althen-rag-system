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
    print("[OK] Environment variables loaded")
except ImportError:
    print("[WARNING] python-dotenv not installed")
except Exception as e:
    print(f"[ERROR] Error loading .env: {e}")

# RAGAnything imports
try:
    from raganything import RAGAnything
    from lightrag.llm.openai import openai_complete_if_cache, openai_embed
    from lightrag import LightRAG
    RAG_ANYTHING_AVAILABLE = True
except ImportError:
    RAG_ANYTHING_AVAILABLE = False
    print("[WARNING] RAGAnything not available - install with: pip install raganything")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EnhancedRAGService:
    def __init__(self):
        # Supabase setup
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_ANON_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("[ERROR] SUPABASE_URL and SUPABASE_ANON_KEY environment variables are required")
        
        self.supabase = create_client(self.supabase_url, self.supabase_key)
        
        # OpenAI setup for RAGAnything
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        
        # RAGAnything setup
        self.rag_anything = None
        self.working_dir = os.getenv("WORKING_DIR", "./rag_storage")
        Path(self.working_dir).mkdir(exist_ok=True)
            
        logger.info("[OK] Enhanced RAG Service initialized")
    
    def initialize_rag_anything(self):
        """Initialize RAGAnything with OpenAI functions"""
        if not RAG_ANYTHING_AVAILABLE:
            logger.error("[ERROR] RAGAnything not installed")
            return False
            
        if not self.openai_api_key:
            logger.error("[ERROR] OPENAI_API_KEY not found")
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
            logger.info("[OK] RAGAnything initialized")
            return True
        except Exception as e:
            logger.error(f"[ERROR] Failed to initialize RAGAnything: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def get_page_with_datasheets(self, limit=1):
        """Get unprocessed pages that have datasheets"""
        try:
            logger.info("[SEARCH] Looking for unprocessed pages with datasheets...")
            
            # Get unprocessed pages
            pages_response = self.supabase.table("new_pages_index").select("*").eq("ingested", False).limit(20).execute()
            logger.info(f"[PAGES] Found {len(pages_response.data)} unprocessed pages")
            
            pages_with_datasheets = []
            for page in pages_response.data:
                # Check for datasheets for this page
                datasheets_response = self.supabase.table("new_datasheets_index").select("*").eq("parent_url", page["url"]).limit(5).execute()
                if datasheets_response.data:
                    page["datasheets"] = datasheets_response.data
                    pages_with_datasheets.append({
                        "page": page,
                        "datasheet_count": len(datasheets_response.data)
                    })
                    logger.info(f"[OK] Page {page['id']} has {len(datasheets_response.data)} datasheets")
            
            # Sort by datasheet count and limit
            pages_with_datasheets.sort(key=lambda x: x["datasheet_count"], reverse=True)
            return pages_with_datasheets[:limit]
            
        except Exception as e:
            logger.error(f"[ERROR] Error getting pages with datasheets: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def scrape_page_content(self, url):
        """Scrape web page content"""
        try:
            logger.info(f"Scraping page: {url}")
            
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            for script in soup(["script", "style"]):
                script.decompose()
            
            title = soup.title.string if soup.title else "Untitled"
            text = soup.get_text()
            
            # Clean text
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = ' '.join(chunk for chunk in chunks if chunk)
            
            return {
                "title": title,
                "content": clean_text,
                "url": url
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Error scraping page {url}: {e}")
            return None
    
    async def download_datasheet(self, datasheet_url):
        """Download and convert PDF datasheet to text"""
        try:
            logger.info(f"[DOWNLOAD] Downloading datasheet: {datasheet_url}")
            
            response = requests.get(datasheet_url, timeout=30)
            response.raise_for_status()
            
            # Save to temp file and convert to base64
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                temp_file.write(response.content)
                temp_path = temp_file.name
            
            # Convert to base64 for storage
            with open(temp_path, 'rb') as f:
                base64_content = base64.b64encode(f.read()).decode('utf-8')
            
            # Clean up
            os.unlink(temp_path)
            
            return {
                "url": datasheet_url,
                "base64_content": base64_content,
                "size": len(base64_content)
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Error downloading datasheet {datasheet_url}: {e}")
            return None
    
    async def merge_content_for_rag(self, page_content, datasheets_data, page_record):
        """Merge page and datasheet content for RAG processing"""
        try:
            # Create merged content structure
            merged_content = {
                "page_info": {
                    "id": page_record["id"],
                    "url": page_record["url"],
                    "title": page_content["title"],
                    "business_area": page_record["business_area"],
                    "page_type": page_record["page_type"]
                },
                "web_content": page_content["content"][:3000],  # Limit for initial testing
                "datasheets": [],
                "summary": f"Product information for {page_content['title']} with {len(datasheets_data)} technical datasheets"
            }
            
            # Add datasheet info
            for ds in datasheets_data[:3]:  # Limit to first 3 for testing
                if ds:
                    merged_content["datasheets"].append({
                        "url": ds["url"],
                        "size": ds["size"],
                        "type": "PDF technical datasheet"
                    })
            
            return merged_content
            
        except Exception as e:
            logger.error(f"[ERROR] Error merging content: {e}")
            return None
    
    async def process_with_rag_anything(self, merged_content, output_dir):
        """Process merged content through RAGAnything"""
        if not self.rag_anything:
            logger.error("[ERROR] RAGAnything not initialized")
            return None
        
        try:
            # Create a temporary text file with merged content
            content_text = f"""
PRODUCT: {merged_content['page_info']['title']}
BUSINESS AREA: {merged_content['page_info']['business_area']}
URL: {merged_content['page_info']['url']}

WEB CONTENT:
{merged_content['web_content']}

TECHNICAL DATASHEETS:
"""
            
            for ds in merged_content['datasheets']:
                content_text += f"- {ds['url']} ({ds['size']} bytes, {ds['type']})\n"
            
            content_text += f"\nSUMMARY: {merged_content['summary']}"
            
            # Save to temporary file
            temp_file = os.path.join(output_dir, f"merged_content_{merged_content['page_info']['id']}.txt")
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(content_text)
            
            logger.info(f"Created merged content file: {temp_file}")
            
            # Process through RAGAnything
            logger.info("[START] Processing through RAGAnything...")
            await self.rag_anything.process_document_complete(
                file_path=temp_file,
                output_dir=output_dir,
                parse_method="auto"
            )
            
            logger.info("[OK] RAGAnything processing complete")
            return temp_file
            
        except Exception as e:
            logger.error(f"[ERROR] Error processing with RAGAnything: {e}")
            return None
    
    async def query_knowledge_graph(self, question, mode="hybrid"):
        """Query the RAGAnything knowledge graph"""
        if not self.rag_anything:
            logger.error("[ERROR] RAGAnything not initialized")
            return None
        
        try:
            logger.info(f"[SEARCH] Querying: {question}")
            result = await self.rag_anything.query_with_multimodal(question, mode=mode)
            return result
        except Exception as e:
            logger.error(f"[ERROR] Error querying knowledge graph: {e}")
            return None
    
    async def process_complete_example(self):
        """Complete example: page + datasheets -> RAGAnything"""
        try:
            logger.info("[START] Starting complete RAG pipeline...")
            
            # Initialize RAGAnything
            if not self.initialize_rag_anything():
                return {"error": "Failed to initialize RAGAnything"}
            
            # Get a page with datasheets
            pages_with_datasheets = await self.get_page_with_datasheets(limit=1)
            if not pages_with_datasheets:
                return {"error": "No pages with datasheets found"}
            
            page_data = pages_with_datasheets[0]
            page_record = page_data["page"]
            datasheet_count = page_data["datasheet_count"]
            
            logger.info(f"[PAGES] Processing page: {page_record['url']} ({datasheet_count} datasheets)")
            
            # Scrape page content
            page_content = await self.scrape_page_content(page_record["url"])
            if not page_content:
                return {"error": "Failed to scrape page content"}
            
            # Download first few datasheets
            datasheets = page_record.get("datasheets", [])[:2]  # Limit for testing
            datasheets_data = []
            
            for ds in datasheets:
                ds_data = await self.download_datasheet(ds["url"])
                datasheets_data.append(ds_data)
            
            # Merge content
            merged_content = await self.merge_content_for_rag(page_content, datasheets_data, page_record)
            if not merged_content:
                return {"error": "Failed to merge content"}
            
            # Process through RAGAnything
            output_dir = "./rag_output"
            Path(output_dir).mkdir(exist_ok=True)
            
            processed_file = await self.process_with_rag_anything(merged_content, output_dir)
            if not processed_file:
                return {"error": "Failed to process with RAGAnything"}
            
            # Test query
            query_result = await self.query_knowledge_graph(
                "What are the key features and specifications of this product?"
            )
            
            return {
                "status": "success",
                "page_id": page_record["id"],
                "page_url": page_record["url"],
                "page_title": page_content["title"],
                "datasheets_processed": len([d for d in datasheets_data if d]),
                "processed_file": processed_file,
                "query_result": query_result,
                "merged_content_summary": merged_content["summary"]
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Error in complete example: {e}")
            return {"error": str(e)}

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced RAG Service with RAGAnything")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Commands
    complete_cmd = subparsers.add_parser('complete', help='Run complete RAG pipeline example')
    query_cmd = subparsers.add_parser('query', help='Query the knowledge graph')
    query_cmd.add_argument('question', help='Question to ask')
    query_cmd.add_argument('--mode', default='hybrid', choices=['hybrid', 'local', 'global'], help='Query mode')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    try:
        service = EnhancedRAGService()
        
        if args.command == 'complete':
            print("[START] Running complete RAG pipeline...")
            result = await service.process_complete_example()
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
        elif args.command == 'query':
            if not service.initialize_rag_anything():
                print("[ERROR] Failed to initialize RAGAnything")
                return 1
            
            result = await service.query_knowledge_graph(args.question, args.mode)
            print(f"Query: {args.question}")
            print(f"Result: {result}")
        
        return 0
        
    except Exception as e:
        logger.error(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(asyncio.run(main()))