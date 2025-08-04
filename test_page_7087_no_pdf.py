#!/usr/bin/env python3
"""
Test processing page 7087 (no PDFs) and uploading to LightRAG server
"""

import os
import asyncio
import aiohttp
import json
from datetime import datetime
from dotenv import load_dotenv
from scripts.raganything_api_service import (
    fetch_page_data, 
    fetch_datasheets,
    get_supabase_client
)
import requests
from bs4 import BeautifulSoup

# Load environment
load_dotenv()

async def scrape_web_page(url: str) -> str:
    """Scrape content from web page"""
    try:
        print(f"   Scraping web page: {url}")
        
        # Use requests for simpler web scraping
        response = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract title
            title = soup.find('title')
            title_text = title.text.strip() if title else "Unknown Page"
            
            # Extract main content areas
            content_parts = []
            
            # Try to find main content
            main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content')
            if main_content:
                # Extract text from main content
                text = main_content.get_text(separator=' ', strip=True)
                content_parts.append(text[:5000])  # Limit to 5000 chars
            
            # Extract headings
            headings = []
            for h in soup.find_all(['h1', 'h2', 'h3']):
                heading_text = h.get_text(strip=True)
                if heading_text:
                    headings.append(heading_text)
            
            # Extract meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            description = meta_desc.get('content', '') if meta_desc else ''
            
            # Extract product information if available
            product_info = []
            for elem in soup.find_all(['div', 'section'], class_=lambda x: x and ('product' in x.lower() or 'sensor' in x.lower())):
                text = elem.get_text(separator=' ', strip=True)[:500]
                if text and text not in product_info:
                    product_info.append(text)
            
            # Build comprehensive content
            content = f"""
# {title_text}

## Page Information
- **URL:** {url}
- **Scraped at:** {datetime.now().isoformat()}
- **Description:** {description if description else 'Althen Sensors product page'}

## Page Headings
{chr(10).join([f'- {h}' for h in headings[:10]])}

## Main Content
{' '.join(content_parts)}

## Product Information
{chr(10).join(product_info[:5])}

## About Althen Sensors
Althen is a leading provider of high-quality sensors and measurement solutions for various industrial applications. Their product range includes force sensors, pressure sensors, position sensors, torque sensors, and more.

---
*Web page content extracted for knowledge base indexing*
"""
            
            print(f"   Extracted {len(content)} characters from web page")
            return content
            
        else:
            print(f"   Failed to fetch web page: HTTP {response.status_code}")
            return f"Failed to fetch web page content from {url}"
            
    except Exception as e:
        print(f"   Error scraping web page: {e}")
        return f"Error scraping web page: {str(e)}"

async def upload_to_lightrag_server(content: str, metadata: dict = None) -> dict:
    """Upload content to LightRAG server"""
    server_url = os.getenv("LIGHTRAG_SERVER_URL", "").rstrip('/')
    api_key = os.getenv("LIGHTRAG_API_KEY")
    
    if not server_url or not api_key:
        return {"error": "LightRAG server URL or API key not configured"}
    
    try:
        async with aiohttp.ClientSession() as session:
            # Format according to LightRAG API specification
            file_source = f"Page_{metadata.get('page_id', 'unknown')}_WebContent"
            if metadata.get('url'):
                # Extract page name from URL
                url_parts = metadata['url'].rstrip('/').split('/')
                page_name = url_parts[-1] if url_parts else 'unknown'
                file_source += f"__{page_name}"
            
            data = {
                "text": content,
                "file_source": file_source
            }
            
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            
            url = f"{server_url}/documents/text"
            
            async with session.post(url, json=data, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"   [OK] Successfully uploaded to LightRAG server")
                    return {"success": True, "result": result}
                else:
                    error_text = await response.text()
                    print(f"   [ERROR] Upload failed: HTTP {response.status}")
                    return {"error": f"HTTP {response.status}: {error_text[:200]}"}
                    
    except Exception as e:
        print(f"   [ERROR] Upload error: {e}")
        return {"error": str(e)}

async def test_page_7087_processing():
    """Test processing page 7087 (no PDFs, web content only)"""
    print("=== Testing Page 7087 (Web Content Only) ===")
    
    try:
        page_id = 7087
        
        print(f"\n1. Fetching page {page_id} data...")
        page_data = await fetch_page_data(page_id)
        page_url = page_data.get('url')
        print(f"   Page URL: {page_url}")
        print(f"   Business Area: {page_data.get('business_area')}")
        print(f"   Page Type: {page_data.get('page_type')}")
        
        print("\n2. Checking for datasheets...")
        datasheets = await fetch_datasheets(page_id)
        print(f"   Found {len(datasheets)} datasheets")
        
        if datasheets:
            print("   This page has datasheets - unexpected for page 7087!")
            for i, ds in enumerate(datasheets[:3]):
                print(f"     {i+1}. ID: {ds.get('id')}, URL: {ds.get('url')}")
        else:
            print("   No datasheets found (as expected)")
        
        print("\n3. Processing web page content...")
        if page_url:
            web_content = await scrape_web_page(page_url)
            
            print("\n4. Uploading web content to LightRAG server...")
            metadata = {
                "page_id": page_id,
                "url": page_url,
                "business_area": page_data.get('business_area'),
                "page_type": page_data.get('page_type'),
                "timestamp": datetime.now().isoformat(),
                "source": "althen_sensors_web"
            }
            
            upload_result = await upload_to_lightrag_server(web_content, metadata)
            
            if upload_result.get("success"):
                print("   [OK] Successfully uploaded web content to LightRAG server!")
                
                # Mark as processed in Supabase
                supabase = get_supabase_client()
                supabase.table("new_pages_index").update({
                    "ingested": True,
                    "rag_ingested": True,
                    "rag_ingested_at": datetime.now().isoformat()
                }).eq("id", page_id).execute()
                
                print("   [OK] Marked page as processed in Supabase")
                
            else:
                print(f"   [ERROR] Upload failed: {upload_result.get('error')}")
        else:
            print("   [ERROR] No URL found for page")
        
        print("\n5. Test completed!")
        
    except Exception as e:
        print(f"\nError during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_page_7087_processing())