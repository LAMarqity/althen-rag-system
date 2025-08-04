import asyncio
import json
import logging
import os
from datetime import datetime
from supabase import create_client, Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AlthenRAGService:
    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_ANON_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("[ERROR] SUPABASE_URL and SUPABASE_ANON_KEY environment variables are required")
        
        self.supabase = create_client(self.supabase_url, self.supabase_key)
        logger.info("[OK] Supabase client initialized")
    
    def get_stats(self):
        try:
            # Test Supabase connection
            pages_response = self.supabase.table("new_pages_index").select("ingested", count="exact").execute()
            datasheets_response = self.supabase.table("new_datasheets_index").select("ingested", count="exact").execute()
            
            pages_total = pages_response.count or 0
            pages_processed = len([p for p in pages_response.data if p.get("ingested")])
            
            datasheets_total = datasheets_response.count or 0
            datasheets_processed = len([d for d in datasheets_response.data if d.get("ingested")])
            
            return {
                "pages": {
                    "total": pages_total,
                    "processed": pages_processed,
                    "remaining": pages_total - pages_processed
                },
                "datasheets": {
                    "total": datasheets_total,
                    "processed": datasheets_processed,
                    "remaining": datasheets_total - datasheets_processed
                },
                "status": "supabase_connected"
            }
        except Exception as e:
            return {"error": str(e), "status": "supabase_error"}

    async def test_connection(self):
        try:
            # Test getting some unprocessed pages
            response = self.supabase.table("new_pages_index")\
                .select("*")\
                .eq("ingested", False)\
                .limit(3)\
                .execute()
            
            logger.info(f"[PAGES] Found {len(response.data)} unprocessed pages")
            return response.data
        except Exception as e:
            logger.error(f"[ERROR] Error testing connection: {e}")
            return []

    async def list_unprocessed(self, limit=5):
        try:
            # Get unprocessed pages
            pages_response = self.supabase.table("new_pages_index")\
                .select("*")\
                .eq("ingested", False)\
                .limit(limit)\
                .execute()
            
            result = []
            for page in pages_response.data:
                # Get related datasheets
                datasheets_response = self.supabase.table("new_datasheets_index")\
                    .select("*")\
                    .eq("parent_url", page.get("url", ""))\
                    .eq("ingested", False)\
                    .limit(3)\
                    .execute()
                
                result.append({
                    "page": page,
                    "datasheets": datasheets_response.data
                })
            
            return result
        except Exception as e:
            logger.error(f"[ERROR] Error listing unprocessed: {e}")
            return []

    async def list_all_pages(self, limit=5):
        try:
            # Get all pages (regardless of ingested status)
            pages_response = self.supabase.table("new_pages_index")\
                .select("*")\
                .limit(limit)\
                .execute()
            
            return pages_response.data
        except Exception as e:
            logger.error(f"[ERROR] Error listing all pages: {e}")
            return []

    async def reset_pages_for_testing(self, limit=3):
        try:
            # Get some processed pages to reset
            pages_response = self.supabase.table("new_pages_index")\
                .select("*")\
                .eq("ingested", True)\
                .limit(limit)\
                .execute()
            
            if not pages_response.data:
                return []
            
            # Reset their ingested status
            reset_results = []
            for page in pages_response.data:
                result = self.supabase.table("new_pages_index")\
                    .update({"ingested": False})\
                    .eq("id", page["id"])\
                    .execute()
                reset_results.append(page)
            
            return reset_results
        except Exception as e:
            logger.error(f"[ERROR] Error resetting pages: {e}")
            return []

    async def process_web_page_simple(self, page_record):
        """Enkel webbsida-processing utan RAG-Anything"""
        try:
            import requests
            from bs4 import BeautifulSoup
            
            url = page_record.get("url")
            page_id = page_record.get("id")
            
            logger.info(f"Processing page {page_id}: {url}")
            
            # Hämta webbsidan
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # Extrahera text
            soup = BeautifulSoup(response.content, 'html.parser')
            for script in soup(["script", "style"]):
                script.decompose()
            
            title = soup.title.string if soup.title else "Untitled"
            text = soup.get_text()
            
            # Rensa text
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = ' '.join(chunk for chunk in chunks if chunk)
            
            # Begränsa för testning (första 2000 tecken)
            if len(clean_text) > 2000:
                clean_text = clean_text[:2000] + "..."
            
            # Spara i lokal fil för nu
            output_dir = os.path.join("knowledge_base", "processed_pages")
            os.makedirs(output_dir, exist_ok=True)
            
            page_file = os.path.join(output_dir, f"page_{page_id}.json")
            page_data = {
                "id": page_id,
                "url": url,
                "title": title,
                "business_area": page_record.get("business_area"),
                "page_type": page_record.get("page_type"),
                "content": clean_text,
                "content_length": len(clean_text),
                "processed_at": datetime.now().isoformat()
            }
            
            with open(page_file, 'w', encoding='utf-8') as f:
                json.dump(page_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[OK] Page {page_id} processed and saved")
            return {"status": "success", "page_id": page_id, "content_length": len(clean_text)}
            
        except Exception as e:
            logger.error(f"[ERROR] Error processing page {page_id}: {e}")
            return {"status": "error", "page_id": page_id, "message": str(e)}

    async def process_simple_batch(self, max_pages=2):
        """Processa en liten batch av sidor (utan RAG-Anything)"""
        logger.info(f"[START] Starting simple batch processing (max_pages: {max_pages})")
        
        try:
            # Hämta oprocessade sidor
            unprocessed = await self.test_connection()
            if not unprocessed:
                return {"message": "No unprocessed pages found"}
            
            # Begränsa till max_pages
            pages_to_process = unprocessed[:max_pages]
            results = []
            
            for page_record in pages_to_process:
                page_id = page_record["id"]
                
                try:
                    # Processa sidan
                    result = await self.process_web_page_simple(page_record)
                    results.append(result)
                    
                    # Markera som processad om lyckat
                    if result.get("status") == "success":
                        self.supabase.table("new_pages_index")\
                            .update({"ingested": True})\
                            .eq("id", page_id)\
                            .execute()
                        logger.info(f"[OK] Marked page {page_id} as processed")
                    
                except Exception as e:
                    logger.error(f"[ERROR] Error processing page {page_id}: {e}")
                    results.append({"status": "error", "page_id": page_id, "message": str(e)})
            
            successful = len([r for r in results if r.get("status") == "success"])
            
            return {
                "processed": len(results),
                "successful": successful,
                "results": results,
                "note": "Simple text extraction - no RAG yet"
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Error in batch processing: {e}")
            return {"error": str(e)}

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Althen RAG Service (Supabase Test)")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Commands
    stats_cmd = subparsers.add_parser('stats', help='Show processing statistics')
    test_cmd = subparsers.add_parser('test', help='Test Supabase connection')
    list_cmd = subparsers.add_parser('list', help='List unprocessed pages')
    list_cmd.add_argument('--limit', type=int, default=5, help='Number of pages to show')
    all_cmd = subparsers.add_parser('all', help='List all pages')
    all_cmd.add_argument('--limit', type=int, default=5, help='Number of pages to show')
    reset_cmd = subparsers.add_parser('reset', help='Reset some pages for testing')
    reset_cmd.add_argument('--limit', type=int, default=3, help='Number of pages to reset')
    simple_cmd = subparsers.add_parser('simple', help='Simple batch processing (no RAG)')
    simple_cmd.add_argument('--max-pages', type=int, default=2, help='Max pages to process')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    try:
        service = AlthenRAGService()
        
        if args.command == 'stats':
            print("[STATS] Getting statistics...")
            stats = service.get_stats()
            print(json.dumps(stats, indent=2))
            
        elif args.command == 'test':
            print("Testing Supabase connection...")
            unprocessed = await service.test_connection()
            print(f"[OK] Found {len(unprocessed)} unprocessed pages")
            
            if unprocessed:
                print("\nSample page:")
                sample = unprocessed[0]
                print(f"  ID: {sample.get('id')}")
                print(f"  URL: {sample.get('url')}")
                print(f"  Business Area: {sample.get('business_area')}")
                print(f"  Page Type: {sample.get('page_type')}")
                print(f"  Ingested: {sample.get('ingested')}")
            else:
                print("No unprocessed pages found or connection error.")
                
        elif args.command == 'list':
            print(f"[PAGES] Listing {args.limit} unprocessed pages with datasheets...")
            items = await service.list_unprocessed(args.limit)
            
            if not items:
                print("No unprocessed pages found.")
            else:
                for i, item in enumerate(items, 1):
                    page = item['page']
                    datasheets = item['datasheets']
                    
                    print(f"\n{i}. Page ID: {page.get('id')}")
                    print(f"   URL: {page.get('url')}")
                    print(f"   Business Area: {page.get('business_area')}")
                    print(f"   Page Type: {page.get('page_type')}")
                    print(f"   Related datasheets: {len(datasheets)}")
                    
                    for j, ds in enumerate(datasheets[:2], 1):
                        print(f"     {j}. {ds.get('url', 'No URL')}")
                    
                    if len(datasheets) > 2:
                        print(f"     ... and {len(datasheets) - 2} more")

        elif args.command == 'all':
            print(f"[PAGES] Listing {args.limit} pages (all statuses)...")
            pages = await service.list_all_pages(args.limit)
            
            if not pages:
                print("No pages found.")
            else:
                for i, page in enumerate(pages, 1):
                    ingested_status = "[PROCESSED]" if page.get('ingested') else "[PENDING]"
                    print(f"\n{i}. Page ID: {page.get('id')}")
                    print(f"   URL: {page.get('url')}")
                    print(f"   Business Area: {page.get('business_area')}")
                    print(f"   Page Type: {page.get('page_type')}")
                    print(f"   Status: {ingested_status}")
                    print(f"   Created: {page.get('created_at', '')[:19]}")

        elif args.command == 'reset':
            print(f"Resetting {args.limit} pages for testing...")
            reset_pages = await service.reset_pages_for_testing(args.limit)
            
            if reset_pages:
                print(f"[OK] Reset {len(reset_pages)} pages:")
                for page in reset_pages:
                    print(f"  - ID {page.get('id')}: {page.get('url')}")
                print("\nNow you can test processing with 'python start.py test'")
            else:
                print("No pages found to reset.")

        elif args.command == 'simple':
            print(f"[START] Starting simple batch processing ({args.max_pages} pages)...")
            result = await service.process_simple_batch(args.max_pages)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        
        return 0
        
    except Exception as e:
        logger.error(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(asyncio.run(main()))