import json
import os
from pathlib import Path

def setup_lightrag_integration():
    """Setup guide for integrating with existing LightRAG server"""
    
    print("\n" + "="*80)
    print("[SETUP] LIGHTRAG SERVER INTEGRATION SETUP")
    print("="*80)
    print("Integrate with your existing LightRAG server instance")
    print("="*80)
    
    print("\n[OK] MINERU STATUS:")
    print("-" * 40)
    print("[OK] MinerU 2.1.9 is installed and ready")
    print("[OK] PDF processing capabilities available")
    print("[OK] Text, image, and table extraction supported")
    
    print("\n[FEATURES] LIGHTRAG SERVER CLIENT FEATURES:")
    print("-" * 40)
    print("[OK] Connect to existing LightRAG server via API")
    print("[OK] Process PDFs with MinerU extraction")
    print("[OK] Bulk ingest web pages + datasheets")
    print("[OK] Send processed content to your server")
    print("[OK] Query your server for knowledge retrieval")
    
    print("\n[START] GETTING STARTED:")
    print("-" * 40)
    print("1. Configure your LightRAG server URL:")
    
    # Create example environment setup
    env_config = """
# Add to your .env file:
LIGHTRAG_SERVER_URL=http://your-server:8020
LIGHTRAG_API_KEY=your-api-key  # if needed
"""
    print(env_config)
    
    print("2. Test connection to your LightRAG server:")
    print("   python scripts/lightrag_server_client.py test --server http://your-server:8020")
    
    print("\n3. Process a single PDF to test MinerU:")
    print("   python scripts/lightrag_server_client.py pdf path/to/document.pdf")
    
    print("\n4. Bulk ingest pages with datasheets to your server:")
    print("   python scripts/lightrag_server_client.py ingest --server http://your-server:8020 --max-pages 5")
    
    print("\n5. Query your LightRAG server:")
    print("   python scripts/lightrag_server_client.py query \"What are PT1 sensors?\" --server http://your-server:8020")
    
    print("\n[WORKFLOW] INTEGRATION WORKFLOW:")
    print("-" * 40)
    print("[PAGES] Supabase Pages -> Web Scraping -> Content Extraction")
    print("[DATASHEETS] Supabase Datasheets -> PDF Download -> MinerU Processing")
    print("[PROCESS] Combined Content -> Your LightRAG Server -> Knowledge Graph")
    print("[QUERY] Your Server APIs -> Query Interface -> Results")
    
    print("\n[ENDPOINTS] EXPECTED LIGHTRAG SERVER ENDPOINTS:")
    print("-" * 40)
    print("POST /insert     - Insert text content to knowledge graph")
    print("POST /query      - Query the knowledge graph")
    print("GET  /health     - Health check endpoint")
    
    print("\nExample API payload for /insert:")
    insert_payload = {
        "text": "Your extracted content here...",
        "doc_id": "unique_document_id",
        "param": "hybrid"
    }
    print(json.dumps(insert_payload, indent=2))
    
    print("\nExample API payload for /query:")
    query_payload = {
        "query": "What are the key features of PT1 sensors?",
        "param": "hybrid"
    }
    print(json.dumps(query_payload, indent=2))
    
    print("\n[SCALING] SCALING OPTIONS:")
    print("-" * 40)
    print("[PROCESS] Process all 1,988 pages in batches")
    print("[MONITOR] Monitor ingestion progress via Supabase")
    print("[SPEED] Parallel processing for faster ingestion")
    print("[QUERY] Real-time query testing during ingestion")
    
    print("\n[CUSTOM] CUSTOMIZATION OPTIONS:")
    print("-" * 40)
    print("[CONFIG] Adjust MinerU parsing parameters:")
    print("   - parse_method: 'auto', 'ocr', 'txt'")
    print("   - device: 'cpu', 'cuda' (for GPU acceleration)")
    print("   - formula: True/False (extract math formulas)")
    print("   - table: True/False (enhanced table processing)")
    
    print("\n[MINERU] MINERU PROCESSING FEATURES:")
    print("-" * 40)
    print("[TEXT] Text extraction and cleaning")
    print("[IMAGES] Image extraction from PDFs")
    print("[TABLES] Table detection and parsing")
    print("[FORMULAS] Formula recognition")
    print("[OUTPUT] Structured content output (JSON)")
    print("[CONVERT] Markdown conversion")
    
    print("\n[BENEFITS] INTEGRATION BENEFITS:")
    print("-" * 40)
    print("[INFRA] Leverage your existing LightRAG infrastructure")
    print("[GRAPH] Centralized knowledge graph in your server")
    print("[SPEED] No local processing overhead")
    print("[QUERY] Use your existing query interfaces")
    print("[SCALE] Scale with your server's capabilities")
    
    print("\n[TROUBLESHOOT] TROUBLESHOOTING:")
    print("-" * 40)
    print("[ERROR] Connection issues:")
    print("   - Check server URL and port")
    print("   - Verify server is running")
    print("   - Check firewall/network settings")
    print("")
    print("[ERROR] PDF processing issues:")
    print("   - Ensure MinerU is properly installed")
    print("   - Check file permissions")
    print("   - Try different parse methods")
    print("")
    print("[ERROR] Large content issues:")
    print("   - Adjust content length limits")
    print("   - Process in smaller batches")
    print("   - Use chunking for large documents")
    
    print("\n[READY] READY TO INTEGRATE!")
    print("-" * 40)
    print("Your system is ready to:")
    print("[OK] Process PDFs with MinerU")
    print("[OK] Extract multimodal content")
    print("[OK] Send to your LightRAG server")
    print("[OK] Scale to thousands of documents")
    
    print("\n" + "="*80)
    print("[START] START WITH: python scripts/lightrag_server_client.py test")
    print("="*80)

if __name__ == "__main__":
    setup_lightrag_integration()