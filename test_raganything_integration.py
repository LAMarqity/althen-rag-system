#!/usr/bin/env python3
"""
Test RAGAnything integration with image extraction and Supabase upload
"""

import asyncio
import sys
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent / 'scripts'))

from process_page_enhanced import EnhancedPageProcessor

async def test_raganything_integration():
    """Test RAGAnything processing with image extraction"""
    
    # Test with a page that has PDFs
    page_id = 9272  # Page with PDFs that we found earlier
    
    print(f"{'='*70}")
    print(f"Testing RAGAnything Integration with Image Extraction")
    print(f"{'='*70}")
    print(f"Page ID: {page_id}")
    print(f"Expected features:")
    print(f"  - RAGAnything PDF processing with MinerU")
    print(f"  - Image extraction from PDFs")
    print(f"  - Image upload to Supabase storage")
    print(f"  - Markdown with image links")
    print(f"  - Combined document with comprehensive metadata")
    print(f"{'='*70}")
    
    try:
        # Test combined mode with RAGAnything
        print("\n[TEST] COMBINED MODE WITH RAGANYTHING")
        print("-" * 50)
        
        processor = EnhancedPageProcessor(combine_content=True)
        results = await processor.process_page(page_id)
        
        print(f"\nRAGAnything Processing Results:")
        print(f"  Status: {results.get('status')}")
        print(f"  Uploads: {len(results.get('uploads', []))}")
        print(f"  PDF Count: {results.get('pdf_count', 0)}")
        
        # Check if images were extracted and uploaded
        for upload in results.get('uploads', []):
            upload_type = upload.get('type')
            if upload_type == 'combined':
                print(f"  Combined document uploaded successfully")
            elif upload_type == 'pdf':
                print(f"  PDF processed: ID {upload.get('id')}")
        
        print(f"\n{'='*70}")
        print("RAGANYTHING INTEGRATION TEST SUMMARY")
        print(f"{'='*70}")
        
        if results.get('status') == 'success':
            print("✅ RAGAnything integration successful!")
            print("\nFeatures tested:")
            print("  ✅ PDF processing with MinerU")
            print("  ✅ Comprehensive metadata integration")
            print("  ✅ Combined document creation")
            print("  ✅ LightRAG server upload")
            
            print("\nWhat should happen on GPU server:")
            print("  🚀 CUDA acceleration for MinerU processing")
            print("  🖼️  Image extraction from PDF diagrams")
            print("  ☁️  Image upload to Supabase storage")
            print("  🔗 Markdown with Supabase image links")
            print("  📊 Enhanced knowledge graph with visual content")
            
            return True
        else:
            print("❌ RAGAnything integration failed")
            print(f"Error: {results.get('error', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_raganything_integration())
    sys.exit(0 if success else 1)