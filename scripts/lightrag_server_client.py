import asyncio
import json
import logging
import os
import base64
import tempfile
import requests
import gc
import time
import subprocess
import uuid
import mimetypes
from datetime import datetime
from pathlib import Path
from supabase import create_client, Client
from bs4 import BeautifulSoup

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("[OK] Environment variables loaded")
except ImportError:
    print("[WARNING] python-dotenv not installed")

# MinerU imports for PDF processing
try:
    import subprocess
    MINERU_AVAILABLE = True
    print("[OK] MinerU available for PDF processing")
except ImportError:
    MINERU_AVAILABLE = False
    print("[WARNING] MinerU not available")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LightRAGServerClient:
    def __init__(self, lightrag_server_url="http://localhost:8020"):
        """Initialize client for existing LightRAG server"""
        
        # Supabase setup
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_ANON_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("[ERROR] SUPABASE_URL and SUPABASE_ANON_KEY environment variables are required")
        
        self.supabase = create_client(self.supabase_url, self.supabase_key)
        
        # LightRAG server configuration
        self.lightrag_server_url = lightrag_server_url.rstrip('/')
        self.lightrag_api_key = os.getenv("LIGHTRAG_API_KEY")
        self.working_dir = os.getenv("WORKING_DIR", "./processed_content")
        Path(self.working_dir).mkdir(exist_ok=True)
        
        # Process tracking for async MinerU operations
        self.active_processes = {}  # Track running MinerU processes
        self.background_polling_task = None  # Background task for automatic polling
        self.polling_interval = 30  # seconds between checks
        self.auto_polling_enabled = True  # Enable automatic background polling
        
        if not self.lightrag_api_key:
            logger.warning("[WARNING] LIGHTRAG_API_KEY not found in environment variables")
        
        logger.info(f"[OK] LightRAG Server Client initialized (Server: {self.lightrag_server_url})")
    
    def _get_auth_headers(self):
        """Get authentication headers for LightRAG server"""
        headers = {'Content-Type': 'application/json'}
        if self.lightrag_api_key:
            # Server expects X-API-Key header per OpenAPI spec
            headers['X-API-Key'] = self.lightrag_api_key
        return headers
    
    def _get_upload_auth_headers(self):
        """Get authentication headers for file uploads (no Content-Type)"""
        headers = {}
        if self.lightrag_api_key:
            # Server expects X-API-Key header per OpenAPI spec
            headers['X-API-Key'] = self.lightrag_api_key
        return headers
    
    def test_lightrag_server_connection(self):
        """Test connection to LightRAG server"""
        try:
            # Try root endpoint first, then docs endpoint
            headers = self._get_auth_headers()
            for endpoint in ["", "/docs"]:
                response = requests.get(f"{self.lightrag_server_url}{endpoint}", headers=headers, timeout=10)
                if response.status_code == 200:
                    logger.info(f"[OK] LightRAG server connection successful (endpoint: {endpoint or '/'})")
                    return True
            
            logger.error(f"[ERROR] LightRAG server is not responding to standard endpoints")
            return False
        except requests.RequestException as e:
            logger.error(f"[ERROR] Cannot connect to LightRAG server: {e}")
            return False
    
    def insert_text_to_lightrag(self, text_content, doc_id=None):
        """Insert text content to LightRAG server via file upload"""
        try:
            # Create a temporary text file
            filename = f"{doc_id or 'content'}.txt"
            
            # Prepare the file for upload
            files = {
                'file': (filename, text_content, 'text/plain')
            }
            
            # Get auth headers for file upload
            headers = self._get_upload_auth_headers()
            
            response = requests.post(
                f"{self.lightrag_server_url}/documents/upload",
                files=files,
                headers=headers,
                timeout=300
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"[OK] Text uploaded to LightRAG server")
                logger.debug(f"[DEBUG] LightRAG response: {result}")
                # Handle array response from LightRAG
                if isinstance(result, list) and len(result) > 0:
                    logger.info(f"[INFO] Extracted track_id from array response: {result[0].get('track_id', 'N/A')}")
                    return result[0]  # Return first element if array
                return result
            else:
                logger.error(f"[ERROR] Failed to upload text: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"[ERROR] Error uploading text to LightRAG: {e}")
            return None
    
    def insert_multimodal_content_to_lightrag(self, pdf_path, doc_id=None):
        """Process PDF with RAGAnything/MinerU and upload multimodal content to LightRAG server"""
        try:
            logger.info(f"🔄 Processing PDF with RAGAnything multimodal extraction: {pdf_path}")
            
            # Process PDF with MinerU to extract multimodal content
            pdf_result = self.process_pdf_with_mineru(pdf_path, f"./temp_mineru_output_{doc_id or 'content'}")
            
            if not pdf_result:
                logger.error("[ERROR] Failed to process PDF with MinerU")
                return None
            
            # Create rich multimodal content
            multimodal_content = self._create_multimodal_content(pdf_result, doc_id)
            
            # Upload the multimodal content as a structured file
            return self._upload_multimodal_file(multimodal_content, doc_id)
            
        except Exception as e:
            logger.error(f"[ERROR] Error processing multimodal content: {e}")
            return None
    
    def _create_multimodal_content(self, pdf_result, doc_id):
        """Create structured multimodal content from MinerU results"""
        extraction_method = pdf_result.get("extraction_method", "RAGAnything_MinerU")
        
        content = {
            "document_id": doc_id,
            "extraction_method": extraction_method,
            "content_type": "multimodal" if extraction_method == "RAGAnything_MinerU" else "text_only",
            "text_content": pdf_result.get("extracted_text", ""),
            "structured_content": pdf_result.get("structured_content", {}),
            "metadata": {
                "output_dir": pdf_result.get("output_dir"),
                "files_created": pdf_result.get("files_created", []),
                "extraction_timestamp": datetime.now().isoformat()
            }
        }
        
        # Create a comprehensive text representation that includes table and image descriptions
        if pdf_result.get("structured_content") and extraction_method == "RAGAnything_MinerU":
            enhanced_text = self._enhance_text_with_multimodal_info(
                pdf_result.get("extracted_text", ""), 
                pdf_result.get("structured_content")
            )
            content["enhanced_text"] = enhanced_text
        else:
            # For fallback extractions, just use the text content with a note
            text_content = pdf_result.get("extracted_text", "")
            if extraction_method != "RAGAnything_MinerU":
                content["enhanced_text"] = f"""=== PDF CONTENT EXTRACTED WITH FALLBACK METHOD ===
Extraction Method: {extraction_method}
Note: Full multimodal extraction (images, tables) was not available due to processing constraints.

{text_content}

=== END PDF CONTENT ==="""
            else:
                content["enhanced_text"] = text_content
        
        return content
    
    def _enhance_text_with_multimodal_info(self, base_text, structured_content):
        """Enhance text content with descriptions of images and tables for better RAG"""
        enhanced_text = base_text + "\n\n=== MULTIMODAL CONTENT EXTRACTED BY RAGAnything ===\n"
        
        if isinstance(structured_content, list):
            for i, item in enumerate(structured_content):
                if isinstance(item, dict):
                    content_type = item.get('type', 'unknown')
                    
                    if content_type == 'table':
                        enhanced_text += f"\n[TABLE {i+1}]: {item.get('content', 'Table content extracted')}\n"
                        if 'latex' in item:
                            enhanced_text += f"LaTeX representation: {item['latex']}\n"
                    
                    elif content_type == 'image':
                        enhanced_text += f"\n[IMAGE {i+1}]: {item.get('content', 'Image extracted and available')}\n"
                        if 'path' in item:
                            enhanced_text += f"Image file: {item['path']}\n"
                    
                    elif content_type == 'text':
                        enhanced_text += f"\n{item.get('content', '')}\n"
                        
                    elif content_type == 'formula':
                        enhanced_text += f"\n[FORMULA {i+1}]: {item.get('latex', item.get('content', 'Mathematical formula'))}\n"
        
        return enhanced_text
    
    def _upload_multimodal_file(self, multimodal_content, doc_id):
        """Upload multimodal content as a structured JSON file"""
        try:
            # Create filename
            filename = f"{doc_id or 'multimodal_content'}.json"
            
            # Convert to JSON string
            json_content = json.dumps(multimodal_content, indent=2, ensure_ascii=False)
            
            # Upload the enhanced text content (which includes table/image descriptions)
            text_to_upload = multimodal_content.get("enhanced_text", multimodal_content.get("text_content", ""))
            
            files = {
                'file': (f"{doc_id or 'content'}_enhanced.txt", text_to_upload, 'text/plain')
            }
            
            # Get auth headers for file upload
            headers = self._get_upload_auth_headers()
            
            response = requests.post(
                f"{self.lightrag_server_url}/documents/upload",
                files=files,
                headers=headers,
                timeout=300
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"[OK] Multimodal content uploaded to LightRAG server (enhanced with tables/images)")
                
                # Handle array response from LightRAG
                if isinstance(result, list) and len(result) > 0:
                    result = result[0]  # Use first element if array
                
                # Also save the full structured content locally for reference
                output_file = Path(self.working_dir) / f"{filename}"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(json_content)
                logger.info(f"📄 Full multimodal content saved to: {output_file}")
                
                return {
                    "upload_result": result,
                    "local_file": str(output_file),
                    "content_type": "multimodal_enhanced"
                }
            else:
                logger.error(f"[ERROR] Failed to upload multimodal content: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"[ERROR] Error uploading multimodal file: {e}")
            return None
    
    def query_lightrag_server(self, question, mode="hybrid"):
        """Query the LightRAG server"""
        try:
            payload = {
                "query": question,
                "param": mode
            }
            
            headers = self._get_auth_headers()
            
            response = requests.post(
                f"{self.lightrag_server_url}/query",
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", result)
            else:
                logger.error(f"[ERROR] Query failed: {response.status_code} - {response.text}")
                return f"Error: {response.text}"
                
        except Exception as e:
            logger.error(f"[ERROR] Error querying LightRAG server: {e}")
            return f"Error: {str(e)}"
    
    def setup_storage_bucket(self, bucket_name="rag-images"):
        """Create a public storage bucket for images if it doesn't exist"""
        try:
            # Check if bucket exists
            buckets = self.supabase.storage.list_buckets()
            bucket_exists = any(bucket.name == bucket_name for bucket in buckets)
            
            if not bucket_exists:
                # Create public bucket with correct parameters
                result = self.supabase.storage.create_bucket(bucket_name, options={"public": True})
                logger.info(f"[OK] Created public storage bucket: {bucket_name}")
            else:
                logger.info(f"[OK] Storage bucket already exists: {bucket_name}")
            
            return bucket_name
        except Exception as e:
            logger.error(f"[ERROR] Error setting up storage bucket: {e}")
            # Try to return bucket name anyway if it exists
            try:
                buckets = self.supabase.storage.list_buckets()
                if any(bucket.name == bucket_name for bucket in buckets):
                    logger.info(f"[OK] Using existing bucket: {bucket_name}")
                    return bucket_name
            except:
                pass
            return None
    
    def upload_image_to_storage(self, image_path, bucket_name="rag-images", folder="images"):
        """Upload an image to Supabase Storage and return the public URL"""
        try:
            if not Path(image_path).exists():
                logger.warning(f"[WARNING] Image file not found: {image_path}")
                return None
            
            # Generate unique filename
            file_extension = Path(image_path).suffix
            unique_filename = f"{folder}/{uuid.uuid4().hex}{file_extension}"
            
            # Read image file
            with open(image_path, 'rb') as f:
                file_data = f.read()
            
            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(image_path)
            if not mime_type:
                mime_type = 'image/jpeg'  # Default fallback
            
            # Upload to Supabase Storage
            result = self.supabase.storage.from_(bucket_name).upload(
                unique_filename, 
                file_data,
                {"content-type": mime_type}
            )
            
            if result:
                # Get public URL
                public_url = self.supabase.storage.from_(bucket_name).get_public_url(unique_filename)
                logger.info(f"[OK] Image uploaded to storage: {unique_filename}")
                return public_url
            else:
                logger.error(f"[ERROR] Failed to upload image: {image_path}")
                return None
                
        except Exception as e:
            logger.error(f"[ERROR] Error uploading image to storage: {e}")
            return None
    
    def upload_images_from_directory(self, images_dir, bucket_name="rag-images", folder_prefix=""):
        """Upload all images from a directory to Supabase Storage"""
        try:
            images_dir = Path(images_dir)
            if not images_dir.exists():
                logger.warning(f"[WARNING] Images directory not found: {images_dir}")
                return {}
            
            uploaded_images = {}
            image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']
            
            for image_file in images_dir.iterdir():
                if image_file.suffix.lower() in image_extensions:
                    folder_name = f"{folder_prefix}/{images_dir.name}" if folder_prefix else images_dir.name
                    public_url = self.upload_image_to_storage(
                        str(image_file), 
                        bucket_name, 
                        folder_name
                    )
                    if public_url:
                        uploaded_images[image_file.name] = public_url
            
            logger.info(f"[OK] Uploaded {len(uploaded_images)} images from {images_dir}")
            return uploaded_images
            
        except Exception as e:
            logger.error(f"[ERROR] Error uploading images from directory: {e}")
            return {}
    
    def process_pdf_with_mineru(self, pdf_path, output_dir, fast_text_only=False, low_memory=True):
        """Process PDF using MinerU for text, image, and table extraction"""
        try:
            if not MINERU_AVAILABLE:
                return None
            
            mode = "txt" if fast_text_only else "auto"
            logger.info(f"📄 Processing PDF with MinerU ({mode} mode): {pdf_path}")
            
            # Create output directory
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            # Run MinerU command with optimized RAGAnything settings
            cmd = [
                "mineru",
                "-p", str(pdf_path),
                "-o", str(output_dir),
                "-m", mode,                 # auto=full extraction, txt=fast text-only
                "-l", "en",                 # English language for better OCR performance
                "-d", "cpu",                # Use CPU since CUDA not compiled with PyTorch
                "-b", "pipeline",           # Use pipeline backend for better processing
                "-f", "true",               # Enable formula parsing
                "-t", "true"                # Enable table parsing
            ]
            
            # Set timeout based on mode and memory settings - give full 20 minutes for comprehensive processing
            if low_memory:
                # Still respect low_memory flag but with proper timeout for quality
                timeout = 1200  # 20 minutes for comprehensive multimodal extraction
                logger.info(f"🔧 Low-memory mode: {timeout}s timeout (20 min for quality extraction)")
            else:
                # Standard timeout for comprehensive multimodal extraction
                timeout = 1200  # 20 minutes for comprehensive multimodal extraction
                logger.info(f"🔧 Standard mode: {timeout}s timeout for high-quality multimodal extraction")
            
            logger.info(f"🔧 Running MinerU with RAGAnything settings: {' '.join(cmd)}")
            # Use dynamic timeout based on hardware capabilities
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            
            # Always check for output files regardless of return code
            # MinerU sometimes returns non-zero even when successful
            pdf_name = Path(pdf_path).stem
            auto_dir = Path(output_dir) / pdf_name / "auto"
            
            if result.returncode == 0:
                logger.info("[OK] MinerU processing completed successfully")
            else:
                logger.warning(f"[WARNING] MinerU returned code {result.returncode}, but checking for output files")
                logger.warning(f"[WARNING] MinerU stderr: {result.stderr}")
            
            # Check for output files regardless of return code
            if auto_dir.exists():
                logger.info(f"[OK] Found MinerU output directory: {auto_dir}")
                # Get markdown content
                md_files = list(auto_dir.glob("*.md"))
                if md_files:
                    with open(md_files[0], 'r', encoding='utf-8') as f:
                        extracted_text = f.read()
                    
                    # Get structured content
                    content_list_files = list(auto_dir.glob("*_content_list.json"))
                    structured_content = None
                    if content_list_files:
                        with open(content_list_files[0], 'r', encoding='utf-8') as f:
                            structured_content = json.load(f)
                    
                    logger.info(f"[OK] Successfully extracted {len(extracted_text)} chars from MinerU")
                    return {
                        "extracted_text": extracted_text,
                        "structured_content": structured_content,
                        "output_dir": str(auto_dir),
                        "files_created": [str(f) for f in auto_dir.glob("*")]
                    }
                else:
                    logger.warning(f"[WARNING] Output directory exists but no markdown files found: {auto_dir}")
            else:
                logger.error(f"[ERROR] No MinerU output directory found: {auto_dir}")
            
            # If we get here, MinerU failed or produced no usable output
            if result.returncode != 0:
                logger.error(f"[ERROR] MinerU failed with return code {result.returncode}")
                return None
            else:
                return {"message": "PDF processed but no markdown found"}
                
        except subprocess.TimeoutExpired:
            logger.warning(f"[WARNING] MinerU timeout after {timeout}s, checking for output files: {pdf_path}")
            # Check if MinerU produced output despite timeout
            return self._check_mineru_output_or_fallback(pdf_path, output_dir)
        except Exception as e:
            logger.error(f"[ERROR] Error processing PDF with MinerU: {e}")
            logger.info(f"🔄 Checking for output files or trying fallback: {pdf_path}")
            return self._check_mineru_output_or_fallback(pdf_path, output_dir)
        finally:
            # Force memory cleanup after each PDF to prevent accumulation
            if low_memory:
                gc.collect()
                time.sleep(1)  # Brief pause to allow memory cleanup
    
    def _check_mineru_output_or_fallback(self, pdf_path, output_dir):
        """Check if MinerU produced output despite timeout, otherwise fallback"""
        try:
            pdf_name = Path(pdf_path).stem
            expected_output_dir = Path(output_dir) / pdf_name / "auto"
            
            # Check if MinerU actually produced output
            markdown_file = expected_output_dir / f"{pdf_name}.md"
            content_list_file = expected_output_dir / f"{pdf_name}_content_list.json"
            
            if markdown_file.exists() and content_list_file.exists():
                logger.info(f"[OK] Found MinerU output despite timeout: {pdf_name}")
                
                # Read the rich content
                markdown_content = markdown_file.read_text(encoding='utf-8', errors='ignore')
                
                # Try to read content list for multimodal elements
                try:
                    import json
                    with open(content_list_file, 'r', encoding='utf-8') as f:
                        content_list = json.load(f)
                    
                    return {
                        "extracted_text": markdown_content,
                        "content_list": content_list,
                        "extraction_method": "RAGAnything_MinerU_Success_After_Timeout",
                        "images_dir": str(expected_output_dir / "images") if (expected_output_dir / "images").exists() else None
                    }
                except Exception as json_e:
                    logger.warning(f"[WARNING] Could not read content list, using markdown only: {json_e}")
                    return {
                        "extracted_text": markdown_content,
                        "extraction_method": "RAGAnything_MinerU_Markdown_Only"
                    }
            else:
                logger.warning(f"[WARNING] No MinerU output found, using fallback for: {pdf_name}")
                return self._fallback_text_extraction(pdf_path)
                
        except Exception as e:
            logger.error(f"[ERROR] Error checking MinerU output: {e}")
            return self._fallback_text_extraction(pdf_path)
    
    def _create_enhanced_text_from_content_list(self, base_text, content_list, source_url, images_base_dir=None, upload_to_storage=True):
        """Create enhanced text from MinerU content list with multimodal descriptions and Supabase Storage URLs"""
        enhanced_sections = [f"📄 SOURCE DOCUMENT: {source_url}"]
        enhanced_sections.append(f"🔗 ORIGINAL URL: {source_url}")
        enhanced_sections.append("\nCONTENT:\n")
        
        # Setup storage bucket if uploading images
        bucket_name = None
        if upload_to_storage:
            bucket_name = self.setup_storage_bucket("rag-images")
        
        # Add base text first
        if base_text:
            enhanced_sections.append(base_text)
        
        # Process content list for multimodal elements with Supabase Storage URLs
        tables_found = []
        images_found = []
        
        for item in content_list:
            content_type = item.get("type", "")
            
            if content_type == "table":
                table_html = item.get("table_body", "")
                table_caption = item.get("table_caption", [""])[0] if item.get("table_caption") else ""
                
                # Convert HTML table to readable text
                table_text = self._html_table_to_text(table_html)
                table_desc = f"\n\n📊 TABLE: {table_caption}\n{table_text}\n"
                
                enhanced_sections.append(table_desc)
                tables_found.append(table_caption or f"Table {len(tables_found) + 1}")
                
            elif content_type == "image":
                img_caption = item.get("img_caption", [""])[0] if item.get("img_caption") else ""
                img_path = item.get("img_path", "")
                
                # Upload image to Supabase Storage and get public URL
                public_url = None
                if upload_to_storage and bucket_name and images_base_dir and img_path:
                    # Fix path resolution - img_path already includes "images/" so don't double it
                    if img_path.startswith("images/"):
                        # Remove "images/" prefix since images_base_dir already points to images folder
                        img_filename = img_path[7:]  # Remove "images/" prefix
                        full_local_path = Path(images_base_dir) / img_filename
                    else:
                        full_local_path = Path(images_base_dir) / img_path
                    
                    if full_local_path.exists():
                        # Create folder name from source URL for organization
                        url_hash = str(hash(source_url))[-8:]  # Use last 8 chars of hash for uniqueness
                        folder_name = f"documents/{url_hash}"
                        public_url = self.upload_image_to_storage(
                            str(full_local_path), 
                            bucket_name, 
                            folder_name
                        )
                        logger.info(f"[OK] Uploaded image to Supabase: {img_path} -> {public_url}")
                    else:
                        logger.warning(f"[WARNING] Image file not found: {full_local_path}")
                
                # Create image description with public URL
                if public_url:
                    img_desc = f"\n\n🖼️ IMAGE: {img_caption}\n📷 Public URL: {public_url}\n📁 Original Path: {img_path}\n"
                    image_url = public_url
                elif images_base_dir and img_path:
                    # Fallback to local path if upload failed
                    local_url = f"file:///{Path(images_base_dir) / img_path}"
                    img_desc = f"\n\n🖼️ IMAGE: {img_caption}\n📁 Local URL: {local_url}\n📁 Path: {img_path}\n"
                    image_url = local_url
                else:
                    img_desc = f"\n\n🖼️ IMAGE: {img_caption}\n📁 Location: {img_path}\n"
                    image_url = img_path
                
                enhanced_sections.append(img_desc)
                images_found.append({
                    "caption": img_caption or f"Image {len(images_found) + 1}",
                    "path": img_path,
                    "url": image_url,
                    "public": bool(public_url)
                })
                
            elif content_type == "text" and item.get("text"):
                # Additional text content
                text_content = item.get("text", "").strip()
                if text_content and text_content not in base_text:
                    enhanced_sections.append(f"\n{text_content}")
        
        # Add comprehensive summary with URLs
        if tables_found or images_found:
            summary = "\n\n📋 MULTIMODAL CONTENT SUMMARY:\n"
            summary += f"🔗 Source: {source_url}\n"
            
            if tables_found:
                summary += f"📊 Tables ({len(tables_found)}): {', '.join(tables_found)}\n"
            if images_found:
                summary += f"🖼️ Images ({len(images_found)}):\n"
                public_images = [img for img in images_found if img.get('public')]
                if public_images:
                    summary += f"   📷 Public Images ({len(public_images)}):\n"
                    for i, img in enumerate(public_images, 1):
                        summary += f"      {i}. {img['caption']} - {img['url']}\n"
                local_images = [img for img in images_found if not img.get('public')]
                if local_images:
                    summary += f"   📁 Local Images ({len(local_images)}):\n"
                    for i, img in enumerate(local_images, 1):
                        summary += f"      {i}. {img['caption']} - {img.get('path', 'N/A')}\n"
            
            enhanced_sections.append(summary)
        
        # Add reference footer
        enhanced_sections.append(f"\n\n📚 REFERENCE: For full technical details, see {source_url}")
        
        return "\n".join(enhanced_sections)
    
    def _html_table_to_text(self, html_table):
        """Convert HTML table to readable text format"""
        try:
            # Simple HTML table parsing
            import re
            
            # Remove HTML tags and extract cell content
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html_table, re.DOTALL | re.IGNORECASE)
            text_rows = []
            
            for row in rows:
                cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL | re.IGNORECASE)
                # Clean cell content
                clean_cells = []
                for cell in cells:
                    clean_cell = re.sub(r'<[^>]+>', '', cell).strip()
                    clean_cells.append(clean_cell)
                
                if clean_cells:
                    text_rows.append(" | ".join(clean_cells))
            
            return "\n".join(text_rows) if text_rows else html_table
            
        except Exception as e:
            logger.warning(f"[WARNING] Could not parse HTML table: {e}")
            return html_table
    
    def _fallback_text_extraction(self, pdf_path):
        """Fallback simple text extraction when MinerU fails"""
        try:
            import PyPDF2
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                
                logger.info(f"[OK] Fallback extraction successful: {len(text)} characters")
                return {
                    "extracted_text": text,
                    "extraction_method": "PyPDF2_fallback",
                    "output_dir": None,
                    "files_created": []
                }
        except ImportError:
            logger.warning("[WARNING] PyPDF2 not available, trying basic file read")
            try:
                # Very basic fallback - just return filename info
                filename = Path(pdf_path).name
                return {
                    "extracted_text": f"PDF Document: {filename}\nProcessed with basic extraction due to processing issues.",
                    "extraction_method": "basic_fallback",
                    "output_dir": None,
                    "files_created": []
                }
            except Exception as e:
                logger.error(f"[ERROR] All extraction methods failed: {e}")
                return None
        except Exception as e:
            logger.error(f"[ERROR] Fallback extraction failed: {e}")
            return None
    
    async def start_async_mineru_processing(self, pdf_path, output_dir, doc_id, fast_text_only=False, low_memory=True):
        """Start MinerU processing asynchronously and return process info"""
        try:
            if not MINERU_AVAILABLE:
                return None
            
            mode = "txt" if fast_text_only else "auto"
            logger.info(f"🚀 Starting async MinerU processing ({mode} mode): {pdf_path}")
            
            # Create output directory
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            # Create unique process ID
            process_id = f"mineru_{doc_id}_{uuid.uuid4().hex[:8]}"
            
            # Run MinerU command with optimized RAGAnything settings
            cmd = [
                "mineru",
                "-p", str(pdf_path),
                "-o", str(output_dir),
                "-m", mode,
                "-l", "en",
                "-d", "cpu",
                "-b", "pipeline",
                "-f", "true",
                "-t", "true"
            ]
            
            logger.info(f"🔧 Starting MinerU async process: {process_id}")
            
            # Start the process without waiting
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
            
            # Store process info for tracking
            process_info = {
                "process_id": process_id,
                "pdf_path": pdf_path,
                "output_dir": output_dir,
                "doc_id": doc_id,
                "process": process,
                "started_at": time.time(),
                "status": "running",
                "cmd": cmd
            }
            
            logger.info(f"[OK] MinerU process started async: {process_id} (PID: {process.pid})")
            return process_info
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to start async MinerU processing: {e}")
            return None
    
    async def check_mineru_process_completion(self, process_info):
        """Check if MinerU process has completed and return results"""
        try:
            process_id = process_info["process_id"]
            process = process_info["process"]
            pdf_path = process_info["pdf_path"]
            output_dir = process_info["output_dir"]
            
            # Check if process is still running
            poll_result = process.poll()
            
            if poll_result is None:
                # Process is still running
                elapsed = time.time() - process_info["started_at"]
                return {
                    "status": "running",
                    "process_id": process_id,
                    "elapsed_seconds": elapsed
                }
            
            # Process has finished
            stdout, stderr = process.communicate()
            
            logger.info(f"[OK] MinerU process {process_id} completed with return code: {poll_result}")
            
            # Check for output files regardless of return code
            pdf_name = Path(pdf_path).stem
            auto_dir = Path(output_dir) / pdf_name / "auto"
            
            if auto_dir.exists():
                logger.info(f"[OK] Found MinerU output directory: {auto_dir}")
                
                # Get markdown content
                md_files = list(auto_dir.glob("*.md"))
                if md_files:
                    with open(md_files[0], 'r', encoding='utf-8') as f:
                        extracted_text = f.read()
                    
                    # Get structured content
                    content_list_files = list(auto_dir.glob("*_content_list.json"))
                    structured_content = None
                    if content_list_files:
                        with open(content_list_files[0], 'r', encoding='utf-8') as f:
                            structured_content = json.load(f)
                    
                    logger.info(f"[OK] Successfully extracted {len(extracted_text)} chars from async MinerU process {process_id}")
                    
                    return {
                        "status": "completed",
                        "process_id": process_id,
                        "success": True,
                        "extracted_text": extracted_text,
                        "structured_content": structured_content,
                        "output_dir": str(auto_dir),
                        "files_created": [str(f) for f in auto_dir.glob("*")],
                        "return_code": poll_result,
                        "extraction_method": "RAGAnything_MinerU_Async"
                    }
                else:
                    logger.warning(f"[WARNING] Output directory exists but no markdown files found: {auto_dir}")
            
            # Process completed but no usable output found
            logger.error(f"[ERROR] MinerU process {process_id} completed but no usable output found")
            return {
                "status": "completed",
                "process_id": process_id,
                "success": False,
                "error": f"No output found (return code: {poll_result})",
                "stderr": stderr,
                "return_code": poll_result
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Error checking MinerU process completion: {e}")
            return {
                "status": "error",
                "process_id": process_info.get("process_id", "unknown"),
                "error": str(e)
            }
    
    async def process_pdf_async_with_polling(self, pdf_path, output_dir, doc_id, fast_text_only=False, low_memory=True, poll_interval=30, max_wait_time=1200):
        """Process PDF with MinerU asynchronously, polling for completion"""
        try:
            logger.info(f"🔄 Starting async PDF processing with polling: {pdf_path}")
            
            # Start the MinerU process
            process_info = await self.start_async_mineru_processing(
                pdf_path, output_dir, doc_id, fast_text_only, low_memory
            )
            
            if not process_info:
                logger.error("[ERROR] Failed to start MinerU process")
                return None
            
            process_id = process_info["process_id"]
            start_time = time.time()
            
            logger.info(f"⏱️ Polling for completion every {poll_interval}s (max wait: {max_wait_time}s)")
            
            # Poll for completion
            while True:
                # Check if process is complete
                result = await self.check_mineru_process_completion(process_info)
                
                if result["status"] == "completed":
                    if result["success"]:
                        logger.info(f"[OK] Async MinerU processing completed successfully: {process_id}")
                        return {
                            "extracted_text": result["extracted_text"],
                            "structured_content": result.get("structured_content"),
                            "output_dir": result["output_dir"],
                            "files_created": result["files_created"],
                            "extraction_method": result["extraction_method"],
                            "process_id": process_id,
                            "processing_time": time.time() - start_time
                        }
                    else:
                        logger.error(f"[ERROR] Async MinerU processing failed: {result.get('error', 'Unknown error')}")
                        return None
                
                elif result["status"] == "error":
                    logger.error(f"[ERROR] Error in async MinerU processing: {result.get('error', 'Unknown error')}")
                    return None
                
                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > max_wait_time:
                    logger.warning(f"[WARNING] Async MinerU processing timed out after {elapsed:.1f}s")
                    
                    # Try to terminate the process
                    try:
                        process_info["process"].terminate()
                        await asyncio.sleep(5)  # Give it time to terminate
                        if process_info["process"].poll() is None:
                            process_info["process"].kill()
                    except:
                        pass
                    
                    # Check if we got partial results despite timeout
                    final_result = await self.check_mineru_process_completion(process_info)
                    if final_result.get("success"):
                        logger.info(f"[OK] Got results from timed-out MinerU process: {process_id}")
                        return {
                            "extracted_text": final_result["extracted_text"],
                            "structured_content": final_result.get("structured_content"),
                            "output_dir": final_result["output_dir"],
                            "files_created": final_result["files_created"],
                            "extraction_method": "RAGAnything_MinerU_Async_Timeout_Success",
                            "process_id": process_id,
                            "processing_time": elapsed
                        }
                    
                    return None
                
                # Still running, wait before next poll
                logger.info(f"⏳ MinerU process {process_id} still running ({elapsed:.1f}s elapsed)")
                await asyncio.sleep(poll_interval)
            
        except Exception as e:
            logger.error(f"[ERROR] Error in async PDF processing with polling: {e}")
            return None
    
    async def scrape_page_content(self, url):
        """Scrape web page content"""
        try:
            logger.info(f"🌐 Scraping page: {url}")
            
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
    
    async def download_and_process_datasheet(self, datasheet_url, output_dir):
        """Download PDF datasheet and process with MinerU"""
        try:
            logger.info(f"📄 Downloading and processing datasheet: {datasheet_url}")
            
            response = requests.get(datasheet_url, timeout=300)
            response.raise_for_status()
            
            # Save to temp file
            pdf_filename = datasheet_url.split('/')[-1]
            temp_path = Path(output_dir) / pdf_filename
            
            with open(temp_path, 'wb') as f:
                f.write(response.content)
            
            # Process with MinerU (use low-memory mode for better hardware compatibility)
            extraction_result = self.process_pdf_with_mineru(temp_path, output_dir, fast_text_only=False, low_memory=True)
            
            if extraction_result:
                logger.info(f"[OK] Datasheet processed: {len(extraction_result.get('extracted_text', ''))} characters extracted")
                return {
                    "url": datasheet_url,
                    "local_file": str(temp_path),
                    "extraction": extraction_result,
                    "extracted_text": extraction_result.get("extracted_text", ""),
                    "extraction_method": extraction_result.get("extraction_method", "RAGAnything_MinerU")
                }
            else:
                logger.error(f"[ERROR] Failed to process datasheet: {datasheet_url}")
                return None
                
        except Exception as e:
            logger.error(f"[ERROR] Error processing datasheet {datasheet_url}: {e}")
            return None
    
    async def download_and_start_async_datasheet_processing(self, datasheet_url, output_dir, doc_id):
        """Download PDF datasheet and start async MinerU processing"""
        try:
            logger.info(f"📄 Downloading datasheet for async processing: {datasheet_url}")
            
            response = requests.get(datasheet_url, timeout=300)
            response.raise_for_status()
            
            # Save to temp file
            pdf_filename = datasheet_url.split('/')[-1]
            temp_path = Path(output_dir) / pdf_filename
            
            with open(temp_path, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"[OK] Downloaded datasheet: {temp_path}")
            
            # Start async MinerU processing
            process_info = await self.start_async_mineru_processing(
                temp_path, output_dir, doc_id, fast_text_only=False, low_memory=True
            )
            
            if process_info:
                # Store in active processes
                self.active_processes[process_info["process_id"]] = {
                    **process_info,
                    "datasheet_url": datasheet_url,
                    "local_file": str(temp_path)
                }
                
                logger.info(f"[OK] Started async MinerU processing for datasheet: {process_info['process_id']}")
                return {
                    "process_id": process_info["process_id"],
                    "datasheet_url": datasheet_url,
                    "local_file": str(temp_path),
                    "status": "processing"
                }
            else:
                logger.error(f"[ERROR] Failed to start async processing for datasheet: {datasheet_url}")
                return None
                
        except Exception as e:
            logger.error(f"[ERROR] Error starting async datasheet processing {datasheet_url}: {e}")
            return None
    
    async def check_and_upload_completed_processes(self):
        """Check active processes and upload completed ones to LightRAG"""
        try:
            completed_uploads = []
            processes_to_remove = []
            
            for process_id, process_data in list(self.active_processes.items()):
                # Check if process is complete
                result = await self.check_mineru_process_completion(process_data)
                
                if result["status"] == "completed":
                    if result["success"]:
                        logger.info(f"[OK] MinerU process completed, uploading to LightRAG: {process_id}")
                        
                        # Validate that we have actual content
                        extracted_text = result.get("extracted_text", "")
                        if not extracted_text or len(extracted_text.strip()) < 50:
                            logger.warning(f"[WARNING] Process {process_id} completed but content is too short ({len(extracted_text)} chars)")
                            processes_to_remove.append(process_id)
                            continue
                        
                        # Create multimodal content and upload
                        pdf_result = {
                            "extracted_text": extracted_text,
                            "structured_content": result.get("structured_content"),
                            "output_dir": result["output_dir"],
                            "files_created": result["files_created"],
                            "extraction_method": result["extraction_method"]
                        }
                        
                        multimodal_content = self._create_multimodal_content(pdf_result, process_data["doc_id"])
                        upload_result = self._upload_multimodal_file(multimodal_content, process_data["doc_id"])
                        
                        if upload_result:
                            completed_uploads.append({
                                "process_id": process_id,
                                "doc_id": process_data["doc_id"],
                                "datasheet_url": process_data["datasheet_url"],
                                "upload_result": upload_result,
                                "extraction_result": pdf_result,
                                "processing_time": time.time() - process_data["started_at"]
                            })
                            logger.info(f"[OK] Successfully uploaded completed MinerU process: {process_id}")
                        else:
                            logger.error(f"[ERROR] Failed to upload completed process: {process_id}")
                    else:
                        logger.error(f"[ERROR] MinerU process failed: {process_id} - {result.get('error', 'Unknown error')}")
                    
                    processes_to_remove.append(process_id)
                
                elif result["status"] == "error":
                    logger.error(f"[ERROR] MinerU process error: {process_id} - {result.get('error', 'Unknown error')}")
                    processes_to_remove.append(process_id)
            
            # Remove completed/failed processes
            for process_id in processes_to_remove:
                del self.active_processes[process_id]
            
            return completed_uploads
            
        except Exception as e:
            logger.error(f"[ERROR] Error checking and uploading completed processes: {e}")
            return []
    
    def get_active_processes_status(self):
        """Get status of all active MinerU processes"""
        try:
            status_info = []
            current_time = time.time()
            
            for process_id, process_data in self.active_processes.items():
                elapsed = current_time - process_data["started_at"]
                status_info.append({
                    "process_id": process_id,
                    "doc_id": process_data["doc_id"],
                    "datasheet_url": process_data["datasheet_url"],
                    "elapsed_seconds": elapsed,
                    "status": "running"
                })
            
            return {
                "active_processes": len(self.active_processes),
                "processes": status_info
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Error getting process status: {e}")
            return {"active_processes": 0, "processes": []}
    
    async def start_background_polling(self):
        """Start automatic background polling for MinerU processes"""
        try:
            if self.background_polling_task is not None:
                logger.info("[INFO] Background polling already running")
                return
            
            logger.info(f"🚀 Starting automatic background polling (every {self.polling_interval}s)")
            self.background_polling_task = asyncio.create_task(self._background_polling_loop())
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to start background polling: {e}")
    
    async def stop_background_polling(self):
        """Stop automatic background polling"""
        try:
            if self.background_polling_task is not None:
                logger.info("⏹️ Stopping background polling")
                self.background_polling_task.cancel()
                try:
                    await self.background_polling_task
                except asyncio.CancelledError:
                    pass
                self.background_polling_task = None
                logger.info("[OK] Background polling stopped")
            
        except Exception as e:
            logger.error(f"[ERROR] Error stopping background polling: {e}")
    
    async def _background_polling_loop(self):
        """Main background polling loop"""
        try:
            while self.auto_polling_enabled:
                if self.active_processes:
                    logger.info(f"🔍 Background check: {len(self.active_processes)} active processes")
                    
                    # Check and upload completed processes
                    completed = await self.check_and_upload_completed_processes()
                    
                    if completed:
                        logger.info(f"✅ Background polling uploaded {len(completed)} completed processes")
                        for comp in completed:
                            logger.info(f"   📄 {comp['doc_id']}: {len(comp['extraction_result']['extracted_text'])} chars")
                    
                    # Log remaining active processes
                    if self.active_processes:
                        for process_id, process_data in self.active_processes.items():
                            elapsed = time.time() - process_data["started_at"]
                            logger.info(f"   ⏳ {process_id}: {elapsed:.1f}s elapsed")
                else:
                    # No active processes, sleep longer
                    await asyncio.sleep(self.polling_interval * 2)
                    continue
                
                # Wait before next check
                await asyncio.sleep(self.polling_interval)
                
        except asyncio.CancelledError:
            logger.info("[INFO] Background polling cancelled")
            raise
        except Exception as e:
            logger.error(f"[ERROR] Error in background polling loop: {e}")
    
    async def get_process_status_with_auto_check(self):
        """Get process status and automatically check for completed ones"""
        try:
            # First check for any completed processes
            completed = await self.check_and_upload_completed_processes()
            
            # Get current status
            status = self.get_active_processes_status()
            
            # Add information about completed processes in this check
            result = {
                **status,
                "completed_in_check": len(completed) if completed else 0,
                "background_polling_active": self.background_polling_task is not None and not self.background_polling_task.done()
            }
            
            if completed:
                result["recently_completed"] = [
                    {
                        "process_id": comp["process_id"],
                        "doc_id": comp["doc_id"],
                        "processing_time": comp["processing_time"],
                        "content_length": len(comp["extraction_result"]["extracted_text"]),
                        "upload_success": bool(comp["upload_result"])
                    }
                    for comp in completed
                ]
            
            return result
            
        except Exception as e:
            logger.error(f"[ERROR] Error getting process status with auto check: {e}")
            return self.get_active_processes_status()
    
    async def process_page_with_datasheets_to_lightrag(self, page_record, fast_mode=False):
        """Process a page with its datasheets and send to LightRAG server"""
        try:
            page_id = page_record["id"]
            page_url = page_record["url"]
            
            logger.info(f"🚀 Processing page {page_id} with datasheets")
            
            # 1. Scrape web page content
            page_content = await self.scrape_page_content(page_url)
            if not page_content:
                return {"error": "Failed to scrape page content"}
            
            # 2. Get related datasheets
            datasheets_response = self.supabase.table("new_datasheets_index").select("*").eq("parent_url", page_url).limit(5).execute()
            datasheets = datasheets_response.data
            
            logger.info(f"📋 Found {len(datasheets)} datasheets for page {page_id}")
            
            # 3. Process datasheets with RAGAnything multimodal extraction
            processed_datasheets = []
            multimodal_results = []
            output_dir = Path(self.working_dir) / f"page_{page_id}"
            output_dir.mkdir(exist_ok=True)
            
            if fast_mode:
                logger.info(f"⚡ Fast mode: Processing {len(datasheets[:3])} datasheets with simple text extraction")
            else:
                logger.info(f"🔄 Processing {len(datasheets[:3])} datasheets with RAGAnything multimodal extraction")
            
            # New approach: Start async processing for all datasheets, then check periodically
            started_processes = []
            
            for i, datasheet in enumerate(datasheets[:3], 1):  # Limit to first 3 for testing
                datasheet_doc_id = f"page_{page_id}_datasheet_{i}"
                
                if fast_mode:
                    # Fast mode: Use synchronous processing for immediate results
                    ds_result = await self.download_and_process_datasheet(datasheet["url"], output_dir)
                    if ds_result and ds_result.get("local_file"):
                        # Process with existing fast mode logic
                        text_content = ds_result.get("extracted_text", "")
                        content_list = ds_result.get("content_list", [])
                        
                        if content_list:
                            # We have rich MinerU content - create enhanced text with Supabase Storage URLs
                            images_dir = None
                            if ds_result.get("images_dir"):
                                images_dir = ds_result["images_dir"]
                            elif ds_result.get("output_dir"):
                                potential_images_dir = Path(ds_result["output_dir"]) / "images"
                                if potential_images_dir.exists():
                                    images_dir = str(potential_images_dir)
                            
                            enhanced_text = self._create_enhanced_text_from_content_list(
                                text_content, 
                                content_list, 
                                datasheet["url"], 
                                images_base_dir=images_dir,
                                upload_to_storage=True
                            )
                            simple_upload = self.insert_text_to_lightrag(enhanced_text, datasheet_doc_id)
                            if simple_upload:
                                logger.info(f"[OK] Datasheet {i} processed with rich MinerU content ({len(enhanced_text)} chars)")
                                processed_datasheets.append({
                                    "url": datasheet["url"],
                                    "extraction": ds_result,
                                    "content_type": "rich_mineru",
                                    "content_length": len(enhanced_text),
                                    "fast_upload": simple_upload
                                })
                        elif text_content:
                            simple_upload = self.insert_text_to_lightrag(text_content, datasheet_doc_id)
                            if simple_upload:
                                logger.info(f"[OK] Datasheet {i} processed with simple text extraction ({len(text_content)} chars)")
                                processed_datasheets.append({
                                    "url": datasheet["url"],
                                    "extraction": ds_result,
                                    "content_type": "simple_text",
                                    "content_length": len(text_content),
                                    "fast_upload": simple_upload
                                })
                else:
                    # Async mode: Start MinerU processing without waiting
                    async_result = await self.download_and_start_async_datasheet_processing(
                        datasheet["url"], output_dir, datasheet_doc_id
                    )
                    
                    if async_result:
                        started_processes.append({
                            "index": i,
                            "process_info": async_result,
                            "datasheet": datasheet
                        })
                        logger.info(f"[OK] Started async processing for datasheet {i}: {async_result['process_id']}")
                    else:
                        logger.warning(f"[WARNING] Failed to start async processing for datasheet {i}")
            
            # If we started async processes, start background polling and return immediately
            if started_processes and not fast_mode:
                # Start background polling if not already running
                await self.start_background_polling()
                
                return {
                    "status": "processing_async",
                    "page_id": page_id,
                    "page_url": page_url,
                    "async_processes": len(started_processes),
                    "process_ids": [p["process_info"]["process_id"] for p in started_processes],
                    "background_polling_active": True,
                    "polling_interval_seconds": self.polling_interval,
                    "message": f"Started async MinerU processing for {len(started_processes)} datasheets. Background polling will automatically upload when complete."
                }
            
            # Continue with existing logic for fast_mode or when no async processes were started
            if not started_processes:
                logger.warning("[WARNING] No datasheets were successfully processed")
            
            # 4. Create overview content for LightRAG (this provides context linking web content to PDFs)
            overview_content = f"""
PRODUCT OVERVIEW: {page_content['title']}
BUSINESS AREA: {page_record.get('business_area', 'unknown')}
PAGE TYPE: {page_record.get('page_type', 'unknown')}
SOURCE URL: {page_url}

WEB CONTENT SUMMARY:
{page_content['content'][:2000]}

TECHNICAL DOCUMENTATION OVERVIEW:
This product has {len(processed_datasheets)} technical datasheets that have been processed with RAGAnything multimodal extraction:
"""
            
            # Add datasheet overview (not full content, as that's already ingested separately)
            for i, ds in enumerate(processed_datasheets, 1):
                filename = ds["url"].split('/')[-1]
                overview_content += f"\n• DATASHEET {i}: {filename}"
                if "multimodal_ingestion" in ds:
                    overview_content += " ([OK] Multimodal: tables, images, formulas extracted)"
                else:
                    overview_content += " (📄 Text only)"
            
            overview_content += f"\n\nCOMPLETE SUMMARY: Product '{page_content['title']}' with {len(processed_datasheets)} technical documents fully processed with RAGAnything multimodal capabilities for comprehensive retrieval."
            
            # 5. Send overview to LightRAG server (the detailed PDF content is already uploaded)
            doc_id = f"page_{page_id}_overview"
            insertion_result = self.insert_text_to_lightrag(overview_content, doc_id)
            
            if insertion_result:
                # Mark page as ingested in Supabase with LightRAG track ID
                update_data = {"ingested": True}
                
                # Debug logging
                logger.info(f"[DEBUG] insertion_result type: {type(insertion_result)}")
                logger.info(f"[DEBUG] insertion_result content: {insertion_result}")
                
                # Extract track_id from LightRAG response
                if isinstance(insertion_result, dict) and "track_id" in insertion_result:
                    update_data["lightrag_track_id"] = insertion_result["track_id"]
                    logger.info(f"[OK] Storing LightRAG track ID: {insertion_result['track_id']}")
                else:
                    logger.warning(f"[WARNING] No track_id found in response: {insertion_result}")
                
                # Update Supabase
                update_result = self.supabase.table("new_pages_index").update(update_data).eq("id", page_id).execute()
                logger.info(f"[DEBUG] Supabase update result: {update_result.data[0] if update_result.data else 'No data'}")
                
                logger.info(f"[OK] Page {page_id} successfully ingested to LightRAG server")
                
                return {
                    "status": "success",
                    "page_id": page_id,
                    "page_url": page_url,
                    "overview_content_length": len(overview_content),
                    "datasheets_processed": len(processed_datasheets),
                    "multimodal_extractions": len(multimodal_results),
                    "lightrag_overview_result": insertion_result,
                    "multimodal_results": multimodal_results,
                    "extraction_method": "RAGAnything_MinerU_Multimodal"
                }
            else:
                return {"error": "Failed to insert into LightRAG server"}
                
        except Exception as e:
            logger.error(f"[ERROR] Error processing page {page_id}: {e}")
            return {"error": str(e)}
    
    async def process_specific_page_to_lightrag(self, page_id, fast_mode=False):
        """Process a specific page by ID to LightRAG server"""
        try:
            logger.info(f"🎯 Processing specific page {page_id} to LightRAG server")
            
            # Test server connection first
            if not self.test_lightrag_server_connection():
                return {"error": "Cannot connect to LightRAG server"}
            
            # Get specific page
            page_response = self.supabase.table("new_pages_index").select("*").eq("id", page_id).execute()
            
            if not page_response.data:
                return {"error": f"Page {page_id} not found"}
            
            page = page_response.data[0]
            
            # Check if page has datasheets
            datasheets_response = self.supabase.table("new_datasheets_index").select("*").eq("parent_url", page["url"]).limit(5).execute()
            
            if not datasheets_response.data:
                logger.warning(f"[WARNING] Page {page_id} has no datasheets, processing web content only")
                # Process web content only
                return await self.process_page_web_content_to_lightrag(page)
            
            # Process page with datasheets using Supabase Storage
            result = await self.process_page_with_datasheets_to_lightrag(page, fast_mode=fast_mode)
            
            return {
                "processed": 1,
                "successful": 1 if result.get("status") == "success" else 0,
                "results": [result],
                "lightrag_server": self.lightrag_server_url,
                "page_id": page_id
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Error processing specific page {page_id}: {e}")
            return {"error": f"Error processing page {page_id}: {str(e)}"}

    async def process_page_web_content_to_lightrag(self, page):
        """Process only web content for a page (no datasheets)"""
        try:
            logger.info(f"🌐 Processing web content only for page {page['id']}")
            
            # Scrape web content
            web_content = self.scrape_web_content(page["url"])
            if not web_content:
                return {"status": "error", "page_id": page["id"], "error": "Failed to scrape web content"}
            
            # Create document ID and upload to LightRAG
            doc_id = f"page_{page['id']}_web_content"
            
            # Create enhanced web content with metadata
            enhanced_content = f"""📄 WEB PAGE: {page['url']}
🔗 ORIGINAL URL: {page['url']}
📅 Processed: {datetime.now().isoformat()}

CONTENT:

{web_content}

📚 REFERENCE: For complete information, visit {page['url']}
"""
            
            result = self.insert_text_to_lightrag(enhanced_content, doc_id)
            
            if result:
                # Mark page as ingested with LightRAG track ID
                update_data = {"ingested": True}
                
                # Extract track_id from LightRAG response
                if isinstance(result, dict) and "track_id" in result:
                    update_data["lightrag_track_id"] = result["track_id"]
                    logger.info(f"[OK] Storing LightRAG track ID: {result['track_id']}")
                
                self.supabase.table("new_pages_index").update(update_data).eq("id", page["id"]).execute()
                
                return {
                    "status": "success",
                    "page_id": page["id"],
                    "page_url": page["url"],
                    "content_length": len(enhanced_content),
                    "lightrag_result": result,
                    "extraction_method": "Web_Content_Only"
                }
            else:
                return {"status": "error", "page_id": page["id"], "error": "Failed to upload to LightRAG"}
                
        except Exception as e:
            logger.error(f"[ERROR] Error processing web content for page {page['id']}: {e}")
            return {"status": "error", "page_id": page["id"], "error": str(e)}

    async def bulk_ingest_to_lightrag(self, max_pages=5, fast_mode=False):
        """Bulk ingest pages with datasheets to LightRAG server"""
        try:
            logger.info(f"🚀 Starting bulk ingestion to LightRAG server (max {max_pages} pages)")
            
            # Test server connection first
            if not self.test_lightrag_server_connection():
                return {"error": "Cannot connect to LightRAG server"}
            
            # Get unprocessed pages with datasheets
            pages_response = self.supabase.table("new_pages_index").select("*").eq("ingested", False).limit(20).execute()
            
            pages_with_datasheets = []
            for page in pages_response.data:
                datasheets_response = self.supabase.table("new_datasheets_index").select("*").eq("parent_url", page["url"]).limit(1).execute()
                if datasheets_response.data:
                    pages_with_datasheets.append(page)
            
            # Process pages
            pages_to_process = pages_with_datasheets[:max_pages]
            results = []
            
            for page in pages_to_process:
                result = await self.process_page_with_datasheets_to_lightrag(page, fast_mode=fast_mode)
                results.append(result)
                
                # Small delay to avoid overwhelming the server
                await asyncio.sleep(1)
            
            successful = len([r for r in results if r.get("status") == "success"])
            
            return {
                "processed": len(results),
                "successful": successful,
                "results": results,
                "lightrag_server": self.lightrag_server_url
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Error in bulk ingestion: {e}")
            return {"error": str(e)}

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="LightRAG Server Client for Bulk Ingestion")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Commands
    test_cmd = subparsers.add_parser('test', help='Test LightRAG server connection')
    test_cmd.add_argument('--server', help='LightRAG server URL (default: from LIGHTRAG_SERVER_URL env var or localhost:8020)')
    
    ingest_cmd = subparsers.add_parser('ingest', help='Bulk ingest pages to LightRAG server')
    ingest_cmd.add_argument('--server', help='LightRAG server URL (default: from LIGHTRAG_SERVER_URL env var or localhost:8020)')
    ingest_cmd.add_argument('--max-pages', type=int, default=5, help='Maximum pages to process')
    ingest_cmd.add_argument('--page-id', type=int, help='Process a specific page by ID')
    ingest_cmd.add_argument('--fast-mode', action='store_true', help='Use faster text extraction (skip full multimodal processing)')
    
    query_cmd = subparsers.add_parser('query', help='Query the LightRAG server')
    query_cmd.add_argument('question', help='Question to ask')
    query_cmd.add_argument('--server', help='LightRAG server URL (default: from LIGHTRAG_SERVER_URL env var or localhost:8020)')
    query_cmd.add_argument('--mode', default='hybrid', choices=['hybrid', 'local', 'global'], help='Query mode')
    
    pdf_cmd = subparsers.add_parser('pdf', help='Process a single PDF with MinerU')
    pdf_cmd.add_argument('pdf_path', help='Path to PDF file')
    pdf_cmd.add_argument('--output', default='./mineru_output', help='Output directory')
    
    multimodal_cmd = subparsers.add_parser('multimodal', help='Process PDF with RAGAnything multimodal extraction and upload to LightRAG')
    multimodal_cmd.add_argument('pdf_path', help='Path to PDF file')
    multimodal_cmd.add_argument('--doc-id', default='test_multimodal', help='Document ID for LightRAG')
    
    # Async processing commands
    async_cmd = subparsers.add_parser('async', help='Async MinerU processing commands')
    async_subparsers = async_cmd.add_subparsers(dest='async_command', help='Async operations')
    
    status_cmd = async_subparsers.add_parser('status', help='Check status of active MinerU processes')
    status_cmd.add_argument('--auto-check', action='store_true', help='Also check for completed processes')
    
    check_cmd = async_subparsers.add_parser('check', help='Check and upload completed processes')
    
    polling_cmd = async_subparsers.add_parser('start-polling', help='Start background polling')
    polling_cmd.add_argument('--interval', type=int, default=30, help='Polling interval in seconds')
    
    stop_polling_cmd = async_subparsers.add_parser('stop-polling', help='Stop background polling')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    try:
        # Get server URL from command line argument, environment variable, or default
        server_url = (args.server if hasattr(args, 'server') and args.server is not None 
                     else os.getenv('LIGHTRAG_SERVER_URL', 'http://localhost:8020'))
        client = LightRAGServerClient(server_url)
        
        if args.command == 'test':
            success = client.test_lightrag_server_connection()
            if success:
                print("[OK] LightRAG server connection successful!")
            else:
                print("[ERROR] LightRAG server connection failed!")
                return 1
                
        elif args.command == 'ingest':
            if hasattr(args, 'page_id') and args.page_id is not None:
                # Process specific page
                result = await client.process_specific_page_to_lightrag(args.page_id, fast_mode=getattr(args, 'fast_mode', False))
            else:
                # Bulk process pages
                result = await client.bulk_ingest_to_lightrag(args.max_pages, fast_mode=getattr(args, 'fast_mode', False))
            print(json.dumps(result, indent=2))
            
        elif args.command == 'query':
            answer = client.query_lightrag_server(args.question, args.mode)
            print(f"Question: {args.question}")
            print(f"Mode: {args.mode}")
            print(f"Answer: {answer}")
            
        elif args.command == 'pdf':
            result = client.process_pdf_with_mineru(args.pdf_path, args.output)
            if result:
                print(f"[OK] PDF processed successfully")
                print(f"📄 Extracted text length: {len(result.get('extracted_text', ''))}")
                print(f"📁 Output directory: {result.get('output_dir')}")
                print(f"📂 Files created: {len(result.get('files_created', []))}")
            else:
                print("[ERROR] PDF processing failed")
                
        elif args.command == 'multimodal':
            print(f"🚀 Processing PDF with RAGAnything multimodal extraction: {args.pdf_path}")
            result = client.insert_multimodal_content_to_lightrag(args.pdf_path, args.doc_id)
            if result:
                print(f"[OK] Multimodal content uploaded to LightRAG server successfully!")
                print(f"📄 Document ID: {args.doc_id}")
                print(f"🔄 Content type: {result.get('content_type')}")
                print(f"📁 Local backup: {result.get('local_file')}")
                if result.get('upload_result'):
                    print(f"🌐 Server response: {result['upload_result']}")
            else:
                print("[ERROR] Multimodal processing and upload failed")
                
        elif args.command == 'async':
            if args.async_command == 'status':
                if getattr(args, 'auto_check', False):
                    status = await client.get_process_status_with_auto_check()
                    print(f"🔄 Active MinerU processes: {status['active_processes']}")
                    print(f"🤖 Background polling: {'Active' if status['background_polling_active'] else 'Inactive'}")
                    if status.get('completed_in_check', 0) > 0:
                        print(f"✅ Completed in this check: {status['completed_in_check']}")
                        for comp in status.get('recently_completed', []):
                            print(f"  📄 {comp['doc_id']}: {comp['content_length']} chars, {comp['processing_time']:.1f}s")
                else:
                    status = client.get_active_processes_status()
                    print(f"🔄 Active MinerU processes: {status['active_processes']}")
                
                if status['processes']:
                    for process in status['processes']:
                        elapsed_min = process['elapsed_seconds'] / 60
                        print(f"  📄 {process['process_id']}: {process['doc_id']} ({elapsed_min:.1f}m elapsed)")
                        print(f"     🔗 {process['datasheet_url']}")
                else:
                    print("   No active processes")
                    
            elif args.async_command == 'check':
                print("🔍 Checking for completed MinerU processes...")
                completed = await client.check_and_upload_completed_processes()
                if completed:
                    print(f"[OK] Found {len(completed)} completed processes:")
                    for comp in completed:
                        print(f"  ✅ {comp['process_id']}: {comp['doc_id']}")
                        print(f"     ⏱️ Processing time: {comp['processing_time']:.1f}s")
                        print(f"     📄 Content length: {len(comp['extraction_result']['extracted_text'])} chars")
                        if comp['upload_result']:
                            print(f"     🌐 Upload successful: {comp['upload_result'].get('upload_result', {}).get('track_id', 'N/A')}")
                else:
                    print("   No completed processes found")
                    
            elif args.async_command == 'start-polling':
                client.polling_interval = getattr(args, 'interval', 30)
                await client.start_background_polling()
                print(f"🚀 Background polling started (interval: {client.polling_interval}s)")
                print("   Polling will continue until stopped or program exits")
                
                # Keep running until user interrupts
                try:
                    while client.background_polling_task and not client.background_polling_task.done():
                        await asyncio.sleep(5)
                        status = client.get_active_processes_status()
                        if status['active_processes'] > 0:
                            print(f"   📊 Status: {status['active_processes']} active processes")
                except KeyboardInterrupt:
                    print("\n⏹️ Stopping background polling...")
                    await client.stop_background_polling()
                    
            elif args.async_command == 'stop-polling':
                await client.stop_background_polling()
                print("⏹️ Background polling stopped")
        
        return 0
        
    except Exception as e:
        logger.error(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(asyncio.run(main()))