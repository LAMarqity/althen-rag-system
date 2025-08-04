#!/usr/bin/env python3
"""
Debug script to show exactly what images are extracted vs what's in markdown
"""
import os
import sys
import glob
import json
from pathlib import Path

def debug_mineru_output():
    """Debug what MinerU actually produces"""
    
    # Find all output directories
    output_dirs = glob.glob("output/*/auto/")
    
    if not output_dirs:
        print("❌ No MinerU output directories found")
        return
    
    for output_dir in output_dirs[:3]:  # Check first 3
        print(f"\n{'='*60}")
        print(f"📁 Checking: {output_dir}")
        print(f"{'='*60}")
        
        # Check markdown file
        md_files = glob.glob(f"{output_dir}/*.md")
        if md_files:
            md_file = md_files[0]
            print(f"✅ Found markdown: {os.path.basename(md_file)}")
            
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Count image references in markdown
            image_refs = content.count('![')
            print(f"   📊 Image references in markdown: {image_refs}")
            
            # Find actual image references
            import re
            image_pattern = r'!\[([^\]]*)\]\(([^\)]+)\)'
            matches = re.findall(image_pattern, content)
            print(f"   📸 Actual images referenced:")
            for i, (alt, url) in enumerate(matches[:5]):
                print(f"      {i+1}. Alt: '{alt[:30]}...' | URL: {url[:50]}...")
            if len(matches) > 5:
                print(f"      ... and {len(matches)-5} more")
        else:
            print(f"❌ No markdown file found")
        
        # Check images directory
        images_dir = f"{output_dir}/images"
        if os.path.exists(images_dir):
            image_files = [f for f in os.listdir(images_dir) 
                          if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
            print(f"\n✅ Found images directory: {len(image_files)} files")
            print(f"   📁 First 5 images:")
            for img in image_files[:5]:
                print(f"      - {img}")
            if len(image_files) > 5:
                print(f"      ... and {len(image_files)-5} more")
        else:
            print(f"❌ No images directory found")
        
        # Check content_list.json
        content_list_file = glob.glob(f"{output_dir}/*_content_list.json")
        if content_list_file:
            with open(content_list_file[0], 'r', encoding='utf-8') as f:
                content_list = json.load(f)
            
            # Count different types
            types_count = {}
            images_in_json = []
            tables_in_json = []
            
            for item in content_list:
                item_type = item.get('type', 'unknown')
                types_count[item_type] = types_count.get(item_type, 0) + 1
                
                if item_type == 'image':
                    img_path = item.get('img_path', '')
                    images_in_json.append(os.path.basename(img_path))
                elif item_type == 'table':
                    img_path = item.get('img_path', '')
                    if img_path:
                        tables_in_json.append(os.path.basename(img_path))
            
            print(f"\n✅ Content list analysis:")
            print(f"   📊 Content types: {types_count}")
            print(f"   🖼️ Images in JSON: {len(images_in_json)}")
            print(f"   📊 Tables with images: {len(tables_in_json)}")
            
            # Compare images
            if image_files and images_in_json:
                missing_from_json = set(image_files) - set(images_in_json) - set(tables_in_json)
                missing_from_markdown = set(images_in_json + tables_in_json) - set([os.path.basename(m[1]) for m in matches])
                
                print(f"\n🔍 Image Analysis:")
                print(f"   ❌ Images in directory but NOT in JSON: {len(missing_from_json)}")
                if missing_from_json:
                    for img in list(missing_from_json)[:3]:
                        print(f"      - {img}")
                
                print(f"   ❌ Images in JSON but NOT in markdown: {len(missing_from_markdown)}")
                if missing_from_markdown:
                    for img in list(missing_from_markdown)[:3]:
                        print(f"      - {img}")
        
        # Check web content
        print(f"\n🌐 Web Content Check:")
        if 'Web Page Content' in content or 'web content' in content.lower():
            print(f"   ✅ Web content section found")
        else:
            print(f"   ❌ No web content section found")

if __name__ == "__main__":
    print("🔍 MinerU Output Debug Tool")
    print("="*60)
    debug_mineru_output()