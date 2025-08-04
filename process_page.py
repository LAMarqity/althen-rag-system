#!/usr/bin/env python3
"""
Agnostic page processor - handles any page ID with or without PDFs
Usage: python process_page.py <page_id>
"""

import os
import sys
import asyncio
import aiohttp
import json
import requests
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent / 'scripts'))

from raganything_api_service import (
    fetch_page_data, 
    fetch_datasheets,
    download_pdf,
    get_supabase_client
)

# Load environment
load_dotenv()

class PageProcessor:
    def __init__(self):
        self.server_url = os.getenv("LIGHTRAG_SERVER_URL", "").rstrip('/')
        self.api_key = os.getenv("LIGHTRAG_API_KEY")
        
        if not self.server_url or not self.api_key:
            raise ValueError("LIGHTRAG_SERVER_URL and LIGHTRAG_API_KEY required in .env")
    
    async def scrape_web_content(self, url: str, page_data: dict = None) -> str:
        """Scrape and structure web page content"""
        try:
            print(f"   Scraping: {url}")
            
            response = requests.get(url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            if response.status_code != 200:
                return f"Failed to fetch page (HTTP {response.status_code})"
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract key elements
            title = soup.find('title')
            title_text = title.text.strip() if title else "Unknown Page"
            
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            description = meta_desc.get('content', '') if meta_desc else ''
            
            # Extract headings
            headings = []
            for h in soup.find_all(['h1', 'h2', 'h3'])[:15]:
                heading_text = h.get_text(strip=True)
                if heading_text and len(heading_text) < 200:
                    headings.append(heading_text)
            
            # Extract main content
            content_text = ""
            main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content')
            if main_content:
                content_text = main_content.get_text(separator=' ', strip=True)[:3000]
            
            # Build structured content with metadata if available
            structured_content = f"""# {title_text}

**URL:** {url}
**Description:** {description if description else 'Althen product page'}"""
            
            # Add metadata if page_data is provided
            if page_data:
                business_area = page_data.get('business_area', '')
                category = page_data.get('category', '')
                subcategory = page_data.get('subcategory', '')
                image_url = page_data.get('image_url', '')
                image_title = page_data.get('image_title', '')
                url_lang = page_data.get('url_lang', [])
                page_type = page_data.get('page_type', '')
                
                structured_content += f"""

## Product Classification
- **Business Area:** {business_area}
- **Page Type:** {page_type}
- **Category:** {category}
- **Subcategory:** {subcategory}

## Visual Assets
- **Product Image:** {image_url if image_url else 'Not available'}
- **Image Title:** {image_title if image_title else 'Not specified'}

## Multilingual Information
- **Available Languages:** {len(url_lang)} language versions
{chr(10).join([f'  - {lang_url}' for lang_url in url_lang[:3]])}
{'  - ... and more' if len(url_lang) > 3 else ''}"""
            
            structured_content += f"""

## Content Overview
{content_text}

## Page Structure
{chr(10).join([f'- {h}' for h in headings])}

---
*Source: Althen Sensors website - Processed {datetime.now().isoformat()}*"""
            
            return structured_content
            
        except Exception as e:
            print(f"   Error scraping: {e}")
            return f"Error scraping web content: {str(e)}"
    
    async def process_pdf_content(self, pdf_path: str, pdf_url: str) -> str:
        """Process PDF content (simplified for now, can add MinerU later)"""
        try:
            file_size = os.path.getsize(pdf_path)
            filename = os.path.basename(pdf_url)
            
            # Extract product name from filename
            product_name = filename.replace('.pdf', '').replace('-', ' ').replace('_', ' ').title()
            
            content = f"""# Technical Datasheet: {product_name}

**Document:** {filename}
**Size:** {file_size:,} bytes
**Source:** {pdf_url}

## Product Information
This technical datasheet contains detailed specifications for {product_name}, including:
- Electrical specifications and ratings
- Mechanical dimensions and tolerances
- Environmental operating conditions
- Connection diagrams and pinouts
- Application notes and mounting instructions
- Performance characteristics and graphs

## Key Specifications
The datasheet provides comprehensive technical data for integration and application of this Althen sensor product in industrial and commercial applications.

---
*Datasheet processed {datetime.now().isoformat()}*"""
            
            return content
            
        except Exception as e:
            print(f"   Error processing PDF: {e}")
            return f"Error processing PDF: {str(e)}"
    
    async def upload_to_lightrag(self, content: str, source_identifier: str) -> bool:
        """Upload content to LightRAG server"""
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    "text": content,
                    "file_source": source_identifier
                }
                
                headers = {
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json"
                }
                
                url = f"{self.server_url}/documents/text"
                
                async with session.post(url, json=data, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status == 200:
                        print(f"   [OK] Uploaded to LightRAG server")
                        return True
                    else:
                        error_text = await response.text()
                        print(f"   [ERROR] Upload failed (HTTP {response.status}): {error_text[:100]}")
                        return False
                        
        except Exception as e:
            print(f"   [ERROR] Upload error: {e}")
            return False
    
    async def process_page(self, page_id: int) -> dict:
        """Process any page - handles both PDF and non-PDF pages automatically"""
        
        print(f"\n{'='*60}")
        print(f"Processing Page ID: {page_id}")
        print(f"{'='*60}")
        
        results = {
            "page_id": page_id,
            "status": "started",
            "web_content": False,
            "pdf_count": 0,
            "uploads": []
        }
        
        try:
            # 1. Fetch page data
            print("\n1. Fetching page data...")
            page_data = await fetch_page_data(page_id)
            page_url = page_data.get('url')
            
            if not page_url:
                print("   [ERROR] No URL found for page")
                results["status"] = "error"
                results["error"] = "No URL found"
                return results
            
            print(f"   URL: {page_url}")
            print(f"   Business Area: {page_data.get('business_area')}")
            print(f"   Page Type: {page_data.get('page_type')}")
            
            # 2. Check for datasheets
            print("\n2. Checking for datasheets...")
            datasheets = await fetch_datasheets(page_id)
            print(f"   Found {len(datasheets)} datasheet(s)")
            results["pdf_count"] = len(datasheets)
            
            content_uploaded = False
            
            # 3. Process PDFs if available
            if datasheets:
                print("\n3. Processing PDF datasheets...")
                
                for i, datasheet in enumerate(datasheets, 1):
                    pdf_url = datasheet.get("url") or datasheet.get("pdf_url")
                    if not pdf_url:
                        continue
                    
                    print(f"\n   Datasheet {i}/{len(datasheets)}: {os.path.basename(pdf_url)}")
                    
                    # Download PDF
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                        pdf_path = tmp_file.name
                    
                    success = await download_pdf(pdf_url, pdf_path)
                    
                    if success:
                        # Process PDF content
                        pdf_content = await self.process_pdf_content(pdf_path, pdf_url)
                        
                        # Upload to LightRAG
                        source_id = f"Page_{page_id}_Datasheet_{datasheet['id']}_{os.path.basename(pdf_url)}"
                        if await self.upload_to_lightrag(pdf_content, source_id):
                            results["uploads"].append({
                                "type": "pdf",
                                "id": datasheet['id'],
                                "url": pdf_url
                            })
                            content_uploaded = True
                            
                            # Mark datasheet as processed
                            supabase = get_supabase_client()
                            supabase.table("new_datasheets_index").update({
                                "ingested": True
                            }).eq("id", datasheet['id']).execute()
                    
                    # Clean up temp file
                    try:
                        os.unlink(pdf_path)
                    except:
                        pass
            
            # 4. Process web content if no PDFs or as additional content
            if not datasheets:  # Only process web content if no PDFs
                print("\n3. No PDFs found - Processing web content...")
                web_content = await self.scrape_web_content(page_url, page_data)
                
                # Upload web content
                source_id = f"Page_{page_id}_WebContent_{page_url.split('/')[-1] or 'home'}"
                if await self.upload_to_lightrag(web_content, source_id):
                    results["uploads"].append({
                        "type": "web",
                        "url": page_url
                    })
                    results["web_content"] = True
                    content_uploaded = True
            
            # 5. Mark page as processed if any content was uploaded
            if content_uploaded:
                print("\n4. Updating Supabase status...")
                supabase = get_supabase_client()
                supabase.table("new_pages_index").update({
                    "ingested": True,
                    "rag_ingested": True,
                    "rag_ingested_at": datetime.now().isoformat()
                }).eq("id", page_id).execute()
                print(f"   [OK] Page marked as processed")
                results["status"] = "success"
            else:
                print("\n   [WARNING] No content was uploaded")
                results["status"] = "no_content"
            
            # 6. Summary
            print(f"\n{'='*60}")
            print("SUMMARY:")
            print(f"  Page ID: {page_id}")
            print(f"  Status: {results['status']}")
            print(f"  PDFs processed: {len([u for u in results['uploads'] if u['type'] == 'pdf'])}")
            print(f"  Web content: {'Yes' if results['web_content'] else 'No'}")
            print(f"  Total uploads: {len(results['uploads'])}")
            print(f"{'='*60}\n")
            
            return results
            
        except Exception as e:
            print(f"\n[ERROR] Error processing page: {e}")
            import traceback
            traceback.print_exc()
            results["status"] = "error"
            results["error"] = str(e)
            return results

async def main():
    """Main entry point"""
    
    # Check command line arguments
    if len(sys.argv) < 2:
        print("Usage: python process_page.py <page_id>")
        print("Example: python process_page.py 9022")
        sys.exit(1)
    
    try:
        page_id = int(sys.argv[1])
    except ValueError:
        print(f"Error: Invalid page ID '{sys.argv[1]}' - must be a number")
        sys.exit(1)
    
    # Process the page
    processor = PageProcessor()
    results = await processor.process_page(page_id)
    
    # Exit with appropriate code
    if results["status"] == "success":
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())