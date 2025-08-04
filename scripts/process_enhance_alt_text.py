#!/usr/bin/env python3
"""
Enhanced processing that improves empty alt text in existing images and adds missing ones
"""
import os
import sys
import asyncio
import glob
import tempfile
import requests
import traceback
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.raganything_api_service import (
    get_supabase_client,
    logger,
    initialize_rag,
    upload_image_to_supabase,
    upload_processed_document_to_supabase
)

def scrape_web_content(url: str, max_length: int = 10000) -> str:
    """Extract main content using the new regex-based method"""
    try:
        logger.info(f"Scraping web content from: {url}")
        response = requests.get(url, timeout=30)
        html_data = response.text
        
        # Find first H1 and take everything after it
        h1_match = re.search(r'<h1[^>]*>.*?</h1>', html_data, re.IGNORECASE | re.DOTALL)
        if h1_match:
            # Take everything after first H1
            content_after_h1 = html_data[h1_match.end():]
        else:
            # If no H1 found, take entire content
            content_after_h1 = html_data

        # Patterns for different elements
        patterns = [
            r'<(h[1-6])[^>]*>(.*?)</\1>',  # H-tags
            r'<p[^>]*>(.*?)</p>',          # P-tags
            r'<li[^>]*>(.*?)</li>',        # List items (bullets)
            r'<td[^>]*>(.*?)</td>',        # Table cells
            r'<th[^>]*>(.*?)</th>'         # Table headers
        ]

        # Collect all matches
        all_matches = []
        for pattern in patterns:
            matches = re.findall(pattern, content_after_h1, re.IGNORECASE | re.DOTALL)
            for match in matches:
                if isinstance(match, tuple):
                    content = match[1] if len(match) > 1 else match[0]
                else:
                    content = match
                all_matches.append(content)

        # Clean text
        cleaned_texts = []
        for content in all_matches:
            # Remove all HTML tags
            clean_text = re.sub(r'<[^>]+>', '', content)
            # Remove extra whitespace
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            if clean_text:
                cleaned_texts.append(clean_text)

        web_content = '\n\n'.join(cleaned_texts)
        
        if len(web_content) > max_length:
            web_content = web_content[:max_length] + "..."
        
        logger.info(f"Extracted {len(web_content)} characters of main content")
        return web_content
        
    except Exception as e:
        logger.error(f"Failed to scrape web content: {e}")
        return ""

def convert_table_to_markdown(table) -> str:
    """Convert HTML table to markdown format"""
    try:
        rows = []
        
        # Process table rows
        for tr in table.find_all('tr'):
            cells = []
            for td in tr.find_all(['td', 'th']):
                # Get cell text and clean it
                cell_text = td.get_text(strip=True)
                # Escape pipes in cell content
                cell_text = cell_text.replace('|', '\\|')
                cells.append(cell_text)
            
            if cells:  # Only add non-empty rows
                rows.append('| ' + ' | '.join(cells) + ' |')
        
        if not rows:
            return ""
        
        # Add header separator after first row (if exists)
        if len(rows) > 1:
            header_separator = '|' + '---|' * len(rows[0].split('|')[1:-1]) + '|'
            rows.insert(1, header_separator)
        
        return '\n' + '\n'.join(rows) + '\n'
        
    except Exception as e:
        logger.warning(f"Failed to convert table to markdown: {e}")
        return str(table)  # Fallback to original table HTML

def generate_natural_description(img_info: dict, surrounding_text: str = "") -> str:
    """Generate natural image description using MinerU's own content without rigid categories"""
    
    caption = img_info.get("caption", "").strip()
    footnote = img_info.get("footnote", "").strip()
    img_type = img_info.get("type", "image")
    table_body = img_info.get("table_body", "").strip()
    context = img_info.get("context", "").strip()
    
    # Let MinerU's own extracted content drive the description naturally
    description_parts = []
    
    # Start with MinerU's caption if meaningful
    if caption and len(caption.strip()) > 2:
        # Use MinerU's caption as-is, it's already descriptive
        description_parts.append(caption.strip())
    
    # Add MinerU's footnote if available
    if footnote and len(footnote.strip()) > 2:
        description_parts.append(footnote.strip())
    
    # If we have both caption and footnote, combine naturally
    if len(description_parts) >= 2:
        return " - ".join(description_parts)
    elif len(description_parts) == 1:
        return description_parts[0]
    
    # If no direct MinerU captions, extract meaningful context
    # Look for nearby headings or descriptive text
    if context:
        context_sentences = context.split('.')
        for sentence in context_sentences[:3]:  # Check first 3 sentences
            sentence = sentence.strip()
            if len(sentence) > 20 and len(sentence) < 100:
                # Look for descriptive sentences that might describe the image
                descriptive_keywords = [
                    'shows', 'displays', 'illustrates', 'depicts', 'contains',
                    'specifications', 'dimensions', 'connections', 'configuration',
                    'diagram', 'chart', 'table', 'drawing', 'schematic'
                ]
                
                sentence_lower = sentence.lower()
                if any(keyword in sentence_lower for keyword in descriptive_keywords):
                    return sentence
    
    # Extract meaningful phrases from table content for tables
    if img_type == "table" and table_body:
        # Extract key information from table HTML
        import re
        # Remove HTML tags
        clean_table = re.sub('<[^<]+?>', ' ', table_body)
        # Look for meaningful patterns
        table_words = clean_table.split()[:20]  # First 20 words
        
        # Look for patterns that suggest what the table contains
        meaningful_phrases = []
        for i, word in enumerate(table_words):
            if word.lower() in ['capacity', 'range', 'specification', 'dimension', 'parameter', 'model', 'voltage', 'current', 'temperature', 'pressure']:
                # Take this word and 2-3 following words
                phrase = ' '.join(table_words[i:i+3])
                meaningful_phrases.append(phrase)
        
        if meaningful_phrases:
            return f"Table showing {meaningful_phrases[0].lower()}"
    
    # Fallback: Let surrounding context suggest the content
    if surrounding_text:
        # Extract the most recent heading or meaningful phrase
        sentences = surrounding_text.split('.')
        for sentence in sentences[-3:]:  # Last 3 sentences before image
            sentence = sentence.strip()
            if 10 < len(sentence) < 80:  # Reasonable length
                # Check if it's likely a heading or description
                if sentence.isupper() or sentence.istitle() or ':' in sentence:
                    return sentence
    
    # Final fallback - just indicate it's an image/table without rigid categorization
    if img_type == "table":
        return "Data table"
    else:
        return "Technical diagram"

def extract_images_with_context(content_list_file: str) -> dict:
    """Extract all images with context, indexed by filename"""
    images_map = {}
    try:
        with open(content_list_file, 'r', encoding='utf-8') as f:
            content_list = json.load(f)
        
        # Build context by looking at surrounding text
        for i, item in enumerate(content_list):
            item_type = item.get("type", "")
            
            # Get surrounding text context
            context_text = ""
            for j in range(max(0, i-2), min(len(content_list), i+3)):
                if j != i and content_list[j].get("type") == "text":
                    text = content_list[j].get("text", "").strip()
                    if text:
                        context_text += f" {text}"
            
            if item_type in ["image", "table"]:
                img_path = item.get("img_path", "")
                if img_path:
                    filename = os.path.basename(img_path)
                    
                    # Extract ALL available MinerU data
                    if item_type == "image":
                        caption = " ".join(item.get("image_caption", [])).strip()
                        footnote = " ".join(item.get("image_footnote", [])).strip()
                        table_body = ""
                    else:  # table
                        caption = " ".join(item.get("table_caption", [])).strip()
                        footnote = " ".join(item.get("table_footnote", [])).strip()
                        table_body = item.get("table_body", "").strip()
                    
                    images_map[filename] = {
                        "filename": filename,
                        "caption": caption,
                        "footnote": footnote,
                        "type": item_type,
                        "context": context_text.strip(),
                        "table_body": table_body,
                        "page_idx": item.get("page_idx", 0)
                    }
    
    except Exception as e:
        logger.error(f"Error extracting images from content_list: {e}")
    
    return images_map

def enhance_existing_alt_text(markdown_content: str, image_url_map: dict, images_context_map: dict) -> str:
    """Enhance existing images by improving empty alt text, add missing images separately"""
    
    # First, replace local paths with Supabase URLs
    for local_filename, supabase_url in image_url_map.items():
        patterns = [
            f"images/{local_filename}",
            f"./images/{local_filename}",
            f"auto/images/{local_filename}"
        ]
        for pattern in patterns:
            markdown_content = markdown_content.replace(f"]({pattern})", f"]({supabase_url})")
    
    # Track which images are used in the markdown
    used_images = set()
    
    # Find and enhance images with empty or minimal alt text
    def enhance_alt_text(match):
        alt_text = match.group(1)
        url = match.group(2)
        
        # Extract filename from URL
        filename_match = re.search(r'([^/]+\.(?:jpg|jpeg|png))', url, re.IGNORECASE)
        if not filename_match:
            return match.group(0)  # Return original if can't extract filename
        
        supabase_filename = filename_match.group(1)
        
        # Find the original filename that maps to this Supabase URL
        original_filename = None
        for orig_name, supabase_url in image_url_map.items():
            if supabase_url == url:
                original_filename = orig_name
                break
        
        if not original_filename:
            return match.group(0)  # Return original if can't find mapping
        
        used_images.add(original_filename)
        
        # If alt text is empty or very short, enhance it
        if not alt_text.strip() or len(alt_text.strip()) < 3:
            if original_filename in images_context_map:
                img_info = images_context_map[original_filename]
                natural_alt = generate_natural_description(img_info, img_info["context"])
                logger.info(f"Enhanced empty alt text for {original_filename}: '{natural_alt}'")
                return f"![{natural_alt}]({url})"
        
        # Return original if alt text is already good
        return match.group(0)
    
    # Pattern to match all images: ![alt text](url)
    image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    enhanced_markdown = re.sub(image_pattern, enhance_alt_text, markdown_content)
    
    # Find images that weren't used in the markdown and add them
    unused_images = []
    for filename in image_url_map.keys():
        if filename not in used_images:
            unused_images.append(filename)
    
    if unused_images:
        logger.info(f"Found {len(unused_images)} unused images to add: {unused_images}")
        enhanced_markdown += "\n\n## Additional Technical Documentation\n\n"
        
        for filename in unused_images:
            if filename in image_url_map and filename in images_context_map:
                url = image_url_map[filename]
                img_info = images_context_map[filename]
                natural_description = generate_natural_description(img_info, img_info["context"])
                
                enhanced_markdown += f"![{natural_description}]({url})\n"
                
                # Add MinerU's original context if it provides additional value
                additional_context = []
                if img_info.get('caption') and img_info['caption'] not in natural_description:
                    additional_context.append(f"Caption: {img_info['caption']}")
                if img_info.get('footnote') and img_info['footnote'] not in natural_description:
                    additional_context.append(f"Note: {img_info['footnote']}")
                
                if additional_context:
                    enhanced_markdown += f"*{' | '.join(additional_context)}*\n"
                
                enhanced_markdown += "\n"
    
    return enhanced_markdown

async def process_page_enhance_alt_text(page_id: int):
    """Process page by enhancing alt text without duplicating images"""
    try:
        logger.info(f"Processing page {page_id} by ENHANCING alt text without duplication...")
        
        # Initialize
        supabase_client = get_supabase_client()
        await initialize_rag()
        
        from scripts.raganything_api_service import rag_instance
        if rag_instance is None:
            logger.error("RAG instance is None")
            return {"success": False, "error": "RAG initialization failed"}
        
        # Get page data
        page_response = supabase_client.table("new_pages_index").select("*").eq("id", page_id).execute()
        if not page_response.data:
            logger.error(f"Page {page_id} not found")
            return {"success": False, "error": "Page not found"}
            
        page_data = page_response.data[0]
        page_url = page_data['url']
        logger.info(f"Processing page: {page_url}")
        
        # ALWAYS get web content first
        web_content = scrape_web_content(page_url)
        web_section = ""
        if web_content:
            web_section = f"""## Web Page Content

Source: {page_url}

{web_content}

---
"""
            logger.info("Successfully scraped web content")
        
        # Get datasheets
        datasheets_response = supabase_client.table("new_datasheets_index").select("*").eq("parent_url", page_url).execute()
        datasheets = datasheets_response.data
        logger.info(f"Found {len(datasheets)} datasheets")
        
        all_content_sections = []
        all_images_uploaded = []
        lightrag_track_id = None
        lightrag_content_id = None
        
        if not datasheets:
            # Use web content only
            if not web_content:
                return {"success": False, "error": "No datasheets and no web content available"}
            
            # Get url_lang array from page data
            url_lang = page_data.get('url_lang', [])
            url_lang_section = ""
            if url_lang:
                url_lang_section = f"""
**Available Languages:** {', '.join(url_lang)}
**Language URLs:**
{chr(10).join([f"- {lang}" for lang in url_lang])}
"""

            combined_content = f"""# {page_data.get('category', 'Page')} - {page_data.get('subcategory', 'Web Content')}

**URL:** {page_url}
**Business Area:** {page_data.get('business_area', 'unknown')}
**Page Type:** {page_data.get('page_type', 'web')}{url_lang_section}

---

{web_section}

---
*Processed from web content only - no datasheets available*
"""
        else:
            # Process datasheets with enhanced alt text
            for datasheet in datasheets:
                logger.info(f"Processing datasheet: {datasheet['url']}")
                
                # Download PDF
                response = requests.get(datasheet['url'])
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                    tmp_file.write(response.content)
                    pdf_path = tmp_file.name
                
                try:
                    # Process with RAGAnything
                    await rag_instance.process_document_complete(
                        pdf_path,
                        doc_id=f"page_{page_id}_datasheet_{datasheet['id']}"
                    )
                    
                    # Get MinerU output directory
                    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
                    mineru_output_dir = f"output/{pdf_name}"
                    
                    # Get context for all images FIRST
                    content_list_file = f"{mineru_output_dir}/auto/{pdf_name}_content_list.json"
                    images_context_map = extract_images_with_context(content_list_file)
                    
                    # Process ALL images
                    images_dir = f"{mineru_output_dir}/auto/images"
                    image_url_map = {}
                    
                    if os.path.exists(images_dir):
                        image_files = [f for f in os.listdir(images_dir) 
                                     if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                        
                        logger.info(f"Uploading ALL {len(image_files)} images...")
                        
                        for i, image_file in enumerate(image_files):
                            image_path = os.path.join(images_dir, image_file)
                            
                            # Read image data
                            with open(image_path, 'rb') as img_f:
                                image_data = img_f.read()
                            
                            # Create naturally descriptive filename based on MinerU content
                            if image_file in images_context_map:
                                img_context = images_context_map[image_file]
                                
                                # Use MinerU's own caption/content for filename
                                name_parts = []
                                if img_context.get('caption'):
                                    # Clean caption for filename
                                    clean_caption = re.sub(r'[^a-zA-Z0-9\s]', '', img_context['caption'])
                                    name_parts.extend(clean_caption.lower().split()[:3])  # First 3 words
                                
                                if img_context.get('type') == 'table':
                                    name_parts.append('table')
                                
                                if name_parts:
                                    descriptive_part = "_".join(name_parts)
                                    descriptive_name = f"page_{page_id}_{descriptive_part}_{i+1:03d}.jpg"
                                else:
                                    descriptive_name = f"page_{page_id}_img_{i+1:03d}.jpg"
                            else:
                                descriptive_name = f"page_{page_id}_img_{i+1:03d}.jpg"
                            
                            # Upload to Supabase
                            image_url = await upload_image_to_supabase(
                                image_data,
                                descriptive_name,
                                page_id,
                                datasheet['id']
                            )
                            
                            if image_url:
                                image_url_map[image_file] = image_url
                                all_images_uploaded.append(image_url)
                                
                                if (i + 1) % 10 == 0:
                                    logger.info(f"Uploaded {i+1}/{len(image_files)} images")
                        
                        logger.info(f"Successfully uploaded {len(image_url_map)} images")
                    
                    # Read original markdown and enhance alt text
                    markdown_file = f"{mineru_output_dir}/auto/{pdf_name}.md"
                    if os.path.exists(markdown_file):
                        with open(markdown_file, 'r', encoding='utf-8') as f:
                            original_markdown = f.read()
                        
                        # Enhance alt text without duplicating images
                        pdf_content = enhance_existing_alt_text(original_markdown, image_url_map, images_context_map)
                        logger.info("Enhanced alt text for existing images")
                    else:
                        pdf_content = "No markdown content found"
                    
                    # Create section for this datasheet
                    datasheet_section = f"""## Technical Documentation: {os.path.basename(datasheet['url'])}

{pdf_content}

---
"""
                    all_content_sections.append(datasheet_section)
                    logger.info(f"Added datasheet section with enhanced alt text")
                    
                finally:
                    # Clean up
                    if os.path.exists(pdf_path):
                        os.unlink(pdf_path)
            
            # Get url_lang array from page data
            url_lang = page_data.get('url_lang', [])
            url_lang_section = ""
            if url_lang:
                url_lang_section = f"""
**Available Languages:** {', '.join(url_lang)}
**Language URLs:**
{chr(10).join([f"- {lang}" for lang in url_lang])}
"""

            # Combine all content: web + PDFs
            combined_content = f"""# {page_data.get('category', 'Product')} - {page_data.get('subcategory', 'Documentation')}

**URL:** {page_url}
**Business Area:** {page_data.get('business_area', 'sensors')}
**Page Type:** {page_data.get('page_type', 'product')}{url_lang_section}

---

{web_section}

{"".join(all_content_sections)}

---
*Complete content: Web page + {len(datasheets)} datasheet(s) with {len(all_images_uploaded)} images (enhanced alt text)*
"""
        
        logger.info(f"Created document with ENHANCED alt text: {len(combined_content)} characters, {len(all_images_uploaded)} images")
        
        # Upload to Supabase storage
        doc_url = await upload_processed_document_to_supabase(
            combined_content,
            page_data,
            {
                "processing_method": "enhanced_alt_text_no_duplication",
                "datasheets_processed": len(datasheets),
                "images_uploaded": len(all_images_uploaded),
                "content_length": len(combined_content),
                "includes_web_content": True,
                "enhanced_alt_text": True
            }
        )
        
        # Upload to LightRAG server
        try:
            lightrag_server_url = os.getenv("LIGHTRAG_SERVER_URL", "http://localhost:8020")
            lightrag_api_key = os.getenv("LIGHTRAG_API_KEY")
            
            headers = {'Content-Type': 'application/json'}
            if lightrag_api_key:
                headers['X-API-Key'] = lightrag_api_key
            
            category = page_data.get('category') or 'content'
            safe_category = str(category).lower().replace(' ', '_').replace('-', '_')
            
            payload = {
                "text": combined_content,
                "file_source": f"page_{page_id}_{safe_category}_enhanced_alt"
            }
            
            response = requests.post(
                f"{lightrag_server_url}/documents/text",
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Successfully uploaded to LightRAG server: {result.get('message', 'Success')}")
                track_id = result.get('track_id', 'N/A')
                lightrag_track_id = track_id
                
                # Get the LightRAG content ID using the track_id
                lightrag_content_id = None
                if track_id and track_id != 'N/A':
                    try:
                        track_response = requests.get(
                            f"{lightrag_server_url}/documents/track/{track_id}",
                            headers=headers,
                            timeout=10
                        )
                        
                        if track_response.status_code == 200:
                            track_data = track_response.json()
                            documents = track_data.get('documents', [])
                            if documents:
                                # Get the first document's content ID (assuming single document upload)
                                lightrag_content_id = documents[0].get('id') or documents[0].get('content_id')
                                logger.info(f"Retrieved LightRAG content ID: {lightrag_content_id}")
                            else:
                                logger.warning("No documents found in track response")
                        else:
                            logger.warning(f"Failed to get track status: {track_response.status_code} - {track_response.text}")
                    
                    except Exception as track_error:
                        logger.warning(f"Failed to retrieve LightRAG content ID: {track_error}")
            else:
                logger.warning(f"LightRAG upload failed: {response.status_code} - {response.text}")
                
        except Exception as lightrag_error:
            logger.warning(f"LightRAG upload failed: {lightrag_error}")
            lightrag_track_id = None
            lightrag_content_id = None
        
        # Mark page and datasheets as processed
        page_update_data = {
            "rag_ingested": True,
            "rag_ingested_at": "now()"
        }
        if lightrag_track_id and lightrag_track_id != 'N/A':
            page_update_data["lightrag_track_id"] = lightrag_track_id
        if lightrag_content_id:
            page_update_data["lightrag_content_id"] = lightrag_content_id
            
        supabase_client.table("new_pages_index").update(page_update_data).eq("id", page_id).execute()
        
        if datasheets:
            for datasheet in datasheets:
                datasheet_update_data = {
                    "rag_ingested": True,
                    "rag_ingested_at": "now()"
                }
                if lightrag_track_id and lightrag_track_id != 'N/A':
                    datasheet_update_data["lightrag_track_id"] = lightrag_track_id
                if lightrag_content_id:
                    datasheet_update_data["lightrag_content_id"] = lightrag_content_id
                    
                supabase_client.table("new_datasheets_index").update(datasheet_update_data).eq("id", datasheet['id']).execute()
                logger.info(f"Marked datasheet {datasheet['id']} as processed")
        
        logger.info("ENHANCED ALT TEXT processing complete!")
        
        return {
            "success": True,
            "page_id": page_id,
            "content_length": len(combined_content),
            "images_uploaded": len(all_images_uploaded),
            "datasheets_processed": len(datasheets),
            "doc_url": doc_url,
            "includes_web_content": bool(web_content),
            "enhanced_alt_text": True
        }
        
    except Exception as e:
        logger.error(f"Error processing page {page_id}: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python process_enhance_alt_text.py <page_id>")
        sys.exit(1)
    
    page_id = int(sys.argv[1])
    result = asyncio.run(process_page_enhance_alt_text(page_id))
    
    if result["success"]:
        print(f"""
SUCCESS! ENHANCED ALT TEXT WITHOUT DUPLICATION
Page ID: {result['page_id']}
Content Length: {result['content_length']:,} characters
Images Uploaded: {result['images_uploaded']}
Datasheets Processed: {result['datasheets_processed']}
Web Content Included: {'YES' if result.get('includes_web_content') else 'NO'}
Enhanced Alt Text: {'YES' if result.get('enhanced_alt_text') else 'NO'}
Document URL: {result.get('doc_url', 'N/A')}
""")
    else:
        print(f"FAILED: {result['error']}")