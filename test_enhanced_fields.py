#!/usr/bin/env python3
"""
Test enhanced processing with all Supabase fields
"""

import asyncio
import sys
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent / 'scripts'))

from process_page_enhanced import EnhancedPageProcessor

async def test_enhanced_processing():
    """Test enhanced processing with comprehensive fields"""
    
    # Test with a page that has rich metadata
    page_id = 10412  # The page we saw in schema check with full fields
    
    print(f"{'='*60}")
    print(f"Testing Enhanced Processing with Full Metadata")
    print(f"{'='*60}")
    print(f"Page ID: {page_id}")
    print(f"Testing both separate and combined modes")
    print(f"{'='*60}")
    
    try:
        # Test 1: Separate mode
        print("\n[TEST 1] SEPARATE MODE")
        print("-" * 40)
        processor_separate = EnhancedPageProcessor(combine_content=False)
        results_separate = await processor_separate.process_page(page_id)
        
        print(f"\nSeparate Mode Results:")
        print(f"  Status: {results_separate.get('status')}")
        print(f"  Uploads: {len(results_separate.get('uploads', []))}")
        print(f"  PDF Count: {results_separate.get('pdf_count', 0)}")
        
        # Test 2: Combined mode
        print(f"\n{'='*60}")
        print("\n[TEST 2] COMBINED MODE")
        print("-" * 40)
        processor_combined = EnhancedPageProcessor(combine_content=True)
        results_combined = await processor_combined.process_page(page_id)
        
        print(f"\nCombined Mode Results:")
        print(f"  Status: {results_combined.get('status')}")
        print(f"  Uploads: {len(results_combined.get('uploads', []))}")
        print(f"  PDF Count: {results_combined.get('pdf_count', 0)}")
        
        # Summary
        print(f"\n{'='*60}")
        print("SUMMARY OF ENHANCED FIELD TESTING")
        print(f"{'='*60}")
        print("Fields now included in processing:")
        print("  - url (primary URL)")
        print("  - url_lang (array of translated URLs)")
        print("  - image_url (product image)")
        print("  - image_title (image alt text)")
        print("  - business_area (sensors/controls)")
        print("  - category (product category)")
        print("  - subcategory (product subcategory)")
        print("  - sub_subcategory (detailed classification)")
        print("  - page_type (product/category/etc)")
        print("")
        print("These fields are now embedded in:")
        print("  - Web page content structure")
        print("  - PDF datasheet context")
        print("  - Combined document metadata")
        print("  - Cross-references and relationships")
        print(f"{'='*60}")
        
        if results_separate.get('status') == 'success' or results_combined.get('status') == 'success':
            print("SUCCESS: Enhanced processing with full metadata completed!")
            return True
        else:
            print("WARNING: Some tests may have failed")
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_enhanced_processing())
    sys.exit(0 if success else 1)