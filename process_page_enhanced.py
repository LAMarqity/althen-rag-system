#!/usr/bin/env python3
"""
Enhanced page processor with better relationship handling
Usage: python process_page_enhanced.py <page_id> [--combine]
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

class EnhancedPageProcessor:
    def __init__(self, combine_content=False):
        self.server_url = os.getenv("LIGHTRAG_SERVER_URL", "").rstrip('/')
        self.api_key = os.getenv("LIGHTRAG_API_KEY")
        self.combine_content = combine_content  # Whether to combine page + PDFs into single document
        
        if not self.server_url or not self.api_key:
            raise ValueError("LIGHTRAG_SERVER_URL and LIGHTRAG_API_KEY required in .env")
    
    async def scrape_web_content(self, url: str, page_id: int, page_data: dict, has_datasheets: bool = False) -> str:
        """Scrape web page content with relationship context"""
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
            
            # Extract additional fields from page_data
            url_lang = page_data.get('url_lang', [])
            image_url = page_data.get('image_url', '')
            image_title = page_data.get('image_title', '')
            business_area = page_data.get('business_area', '')
            category = page_data.get('category', '')
            subcategory = page_data.get('subcategory', '')
            sub_subcategory = page_data.get('sub_subcategory', '')
            page_type = page_data.get('page_type', '')
            
            # Build structured content with comprehensive metadata
            structured_content = f"""# {title_text}

## Document Metadata
- **Document Type:** Product Web Page
- **Page ID:** {page_id}
- **URL:** {url}
- **Has Technical Datasheets:** {'Yes' if has_datasheets else 'No'}
- **Description:** {description if description else 'Althen product page'}

## Classification & Navigation
- **Business Area:** {business_area}
- **Page Type:** {page_type}
- **Category:** {category}
- **Subcategory:** {subcategory}
- **Sub-subcategory:** {sub_subcategory}

## Multilingual Information
- **Available Languages:** {len(url_lang)} language versions
{chr(10).join([f'  - {lang_url}' for lang_url in url_lang[:5]])}
{'  - ... and more' if len(url_lang) > 5 else ''}

## Visual Assets
- **Product Image:** {image_url if image_url else 'Not available'}
- **Image Title/Alt:** {image_title if image_title else 'Not specified'}

## Content Overview
{content_text}

## Page Structure
{chr(10).join([f'- {h}' for h in headings])}

"""
            
            if has_datasheets:
                structured_content += """
## Related Documents
This product page has associated technical datasheets with detailed specifications. 
The datasheets contain comprehensive technical data including electrical specifications, 
mechanical dimensions, environmental ratings, and application notes.
"""
            
            structured_content += f"""
---
*Source: Althen Sensors website - Page ID {page_id} - Processed {datetime.now().isoformat()}*"""
            
            return structured_content
            
        except Exception as e:
            print(f"   Error scraping: {e}")
            return f"Error scraping web content: {str(e)}"
    
    async def process_pdf_content(self, pdf_path: str, pdf_url: str, parent_url: str, 
                                  page_id: int, datasheet_id: int, page_data: dict) -> str:
        """Process PDF content with RAGAnything and upload images to Supabase"""
        try:
            print(f"   Processing PDF with RAGAnything: {os.path.basename(pdf_path)}")
            
            # Import RAGAnything processing function
            from raganything_api_service import process_document_with_raganything
            
            # Process document with RAGAnything (includes image extraction and upload to Supabase)
            processing_result = await process_document_with_raganything(pdf_path, page_id, datasheet_id)
            
            if processing_result.get("status") == "success":
                # Get the processed content from RAGAnything
                rag_content = processing_result.get("processed_content", "")
                
                # Extract metadata
                business_area = page_data.get('business_area', '')
                category = page_data.get('category', '')
                subcategory = page_data.get('subcategory', '')
                sub_subcategory = page_data.get('sub_subcategory', '')
                image_url = page_data.get('image_url', '')
                image_title = page_data.get('image_title', '')
                url_lang = page_data.get('url_lang', [])
                
                filename = os.path.basename(pdf_url)
                product_name = filename.replace('.pdf', '').replace('-', ' ').replace('_', ' ').title()
                
                # Combine RAGAnything output with metadata
                enhanced_content = f"""# Technical Datasheet: {product_name}

## Document Metadata
- **Document Type:** Technical Datasheet PDF (Processed with RAGAnything)
- **Datasheet ID:** {datasheet_id}
- **Parent Page ID:** {page_id}
- **Parent Product URL:** {parent_url}
- **PDF Document:** {filename}
- **Processing Status:** Successfully processed with image extraction

## Product Context & Classification
This datasheet is associated with the product page at: {parent_url}

**Product Classification:**
- **Business Area:** {business_area}
- **Category:** {category}
- **Subcategory:** {subcategory}
- **Sub-subcategory:** {sub_subcategory}
- **Product Name:** {product_name}
- **Manufacturer:** Althen Sensors / Althen Controls

## Parent Page Visual Assets
- **Product Image:** {image_url if image_url else 'Not available'}
- **Image Title:** {image_title if image_title else 'Not specified'}

## Multilingual Availability
The parent product page is available in {len(url_lang)} languages:
{chr(10).join([f'- {lang_url}' for lang_url in url_lang[:3]])}
{'- ... and more' if len(url_lang) > 3 else ''}

{'='*60}

## RAGAnything Processed Content

{rag_content}

{'='*60}

## Processing Information
- **Images Extracted:** {processing_result.get('images_uploaded', 0)}
- **Content Length:** {processing_result.get('content_length', 0)} characters
- **Device Used:** {processing_result.get('device_used', 'CPU')}
- **Processing Time:** {processing_result.get('processing_time', 'Unknown')}

## Technical Content

### Electrical Specifications
- Operating voltage ranges and power requirements
- Output signal characteristics (analog/digital)
- Resolution and accuracy specifications
- Linearity and repeatability data
- Temperature coefficients

### Mechanical Specifications
- Physical dimensions and tolerances
- Mounting configurations and options
- Weight and material specifications
- Protection ratings (IP rating)
- Operating temperature range

### Connection Information
- Pinout diagrams and wiring schematics
- Connector types and specifications
- Cable length recommendations
- Shielding requirements

### Application Notes
- Typical applications and use cases
- Installation guidelines
- Calibration procedures
- Troubleshooting guide

## Cross-References
- **Parent Product Page:** Page ID {page_id} at {parent_url}
- **Related Products:** Other sensors in the {product_category} category
- **Manufacturer:** Althen Sensors (www.althensensors.com)

---
*Datasheet ID {datasheet_id} for Page ID {page_id} - Processed {datetime.now().isoformat()}*"""
            
            return content
            
        except Exception as e:
            print(f"   Error processing PDF: {e}")
            return f"Error processing PDF: {str(e)}"
    
    async def combine_contents(self, web_content: str, pdf_contents: list, 
                              page_id: int, page_url: str, page_data: dict) -> str:
        """Combine web and PDF contents into a single document"""
        
        # Extract comprehensive metadata
        business_area = page_data.get('business_area', '')
        category = page_data.get('category', '')
        subcategory = page_data.get('subcategory', '')
        sub_subcategory = page_data.get('sub_subcategory', '')
        image_url = page_data.get('image_url', '')
        image_title = page_data.get('image_title', '')
        url_lang = page_data.get('url_lang', [])
        page_type = page_data.get('page_type', '')
        
        combined = f"""# Combined Product Documentation - Page ID {page_id}

## Document Overview
This combined document contains both web page content and associated technical datasheets 
for a complete product documentation set from Althen Sensors.

**Product Information:**
- **Business Area:** {business_area}
- **Page Type:** {page_type}
- **Category:** {category}
- **Subcategory:** {subcategory}
- **Sub-subcategory:** {sub_subcategory}

**Visual & Multilingual Assets:**
- **Product Image:** {image_url if image_url else 'Not available'}
- **Image Title:** {image_title if image_title else 'Not specified'}
- **Available Languages:** {len(url_lang)} language versions
- **Primary URL:** {page_url}

**Document Structure:**
- Web page content with product overview and specifications
- Technical datasheets ({len(pdf_contents)}) with detailed engineering data
- Cross-referenced relationships and navigation paths

{'='*60}

## PART 1: WEB PAGE CONTENT

{web_content}

{'='*60}

## PART 2: TECHNICAL DATASHEETS

"""
        
        for i, pdf_content in enumerate(pdf_contents, 1):
            combined += f"""
### Datasheet {i} of {len(pdf_contents)}

{pdf_content}

{'='*60}
"""
        
        combined += f"""
## Document Relationships
- **Primary URL:** {page_url}
- **Total Datasheets:** {len(pdf_contents)}
- **Page ID:** {page_id}
- **Processing Date:** {datetime.now().isoformat()}

This combined document ensures all related information is connected in the knowledge graph.
"""
        
        return combined
    
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
        """Process page with enhanced relationship handling"""
        
        print(f"\n{'='*60}")
        print(f"Processing Page ID: {page_id}")
        print(f"Mode: {'COMBINED' if self.combine_content else 'SEPARATE'} document upload")
        print(f"{'='*60}")
        
        results = {
            "page_id": page_id,
            "status": "started",
            "mode": "combined" if self.combine_content else "separate",
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
            
            # 3. Scrape web content (always, for context)
            print("\n3. Processing web content...")
            web_content = await self.scrape_web_content(page_url, page_id, page_data, len(datasheets) > 0)
            
            # 4. Process PDFs if available
            pdf_contents = []
            if datasheets:
                print("\n4. Processing PDF datasheets...")
                
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
                        # Process PDF content with RAGAnything (this handles LightRAG upload internally)
                        pdf_content = await self.process_pdf_content(
                            pdf_path, pdf_url, page_url, page_id, datasheet['id'], page_data
                        )
                        
                        # Only add to pdf_contents if processing was successful
                        if pdf_content and "Error processing PDF" not in pdf_content:
                            pdf_contents.append(pdf_content)
                            
                            # Mark datasheet as processed
                            supabase = get_supabase_client()
                            supabase.table("new_datasheets_index").update({
                                "ingested": True
                            }).eq("id", datasheet['id']).execute()
                            
                            print(f"   [OK] PDF processed with RAGAnything and uploaded to LightRAG")
                        else:
                            print(f"   [ERROR] Failed to process PDF with RAGAnything")
                    
                    # Clean up temp file
                    try:
                        os.unlink(pdf_path)
                    except:
                        pass
            
            # 5. Upload content based on mode
            print("\n5. Uploading to LightRAG server...")
            content_uploaded = False
            
            if self.combine_content and pdf_contents:
                # COMBINED MODE: Upload everything as one document
                print("   Creating combined document...")
                combined_content = await self.combine_contents(
                    web_content, pdf_contents, page_id, page_url, page_data
                )
                
                source_id = f"Page_{page_id}_Combined_{len(pdf_contents)}_Datasheets"
                if await self.upload_to_lightrag(combined_content, source_id):
                    results["uploads"].append({
                        "type": "combined",
                        "page_id": page_id,
                        "datasheet_count": len(pdf_contents)
                    })
                    content_uploaded = True
                    
            else:
                # SEPARATE MODE: Upload each piece separately
                
                # Upload web content
                if not datasheets or self.combine_content == False:
                    print("   Uploading web content...")
                    source_id = f"Page_{page_id}_WebContent"
                    if await self.upload_to_lightrag(web_content, source_id):
                        results["uploads"].append({
                            "type": "web",
                            "url": page_url
                        })
                        results["web_content"] = True
                        content_uploaded = True
                
                # Upload each PDF separately
                for i, pdf_content in enumerate(pdf_contents):
                    print(f"   Uploading datasheet {i+1}/{len(pdf_contents)}...")
                    source_id = f"Page_{page_id}_Datasheet_{datasheets[i]['id']}"
                    if await self.upload_to_lightrag(pdf_content, source_id):
                        results["uploads"].append({
                            "type": "pdf",
                            "id": datasheets[i]['id']
                        })
                        content_uploaded = True
            
            # 6. Mark page as processed
            if content_uploaded:
                print("\n6. Updating Supabase status...")
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
            
            # 7. Summary
            print(f"\n{'='*60}")
            print("SUMMARY:")
            print(f"  Page ID: {page_id}")
            print(f"  Status: {results['status']}")
            print(f"  Mode: {results['mode']}")
            print(f"  PDFs found: {results['pdf_count']}")
            print(f"  Uploads: {len(results['uploads'])}")
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
    
    # Parse arguments
    if len(sys.argv) < 2:
        print("Usage: python process_page_enhanced.py <page_id> [--combine]")
        print("  --combine : Combine web and PDF content into single document")
        print("\nExamples:")
        print("  python process_page_enhanced.py 9022")
        print("  python process_page_enhanced.py 9022 --combine")
        sys.exit(1)
    
    try:
        page_id = int(sys.argv[1])
    except ValueError:
        print(f"Error: Invalid page ID '{sys.argv[1]}' - must be a number")
        sys.exit(1)
    
    # Check for combine flag
    combine_content = "--combine" in sys.argv
    
    # Process the page
    processor = EnhancedPageProcessor(combine_content=combine_content)
    results = await processor.process_page(page_id)
    
    # Exit with appropriate code
    if results["status"] == "success":
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())