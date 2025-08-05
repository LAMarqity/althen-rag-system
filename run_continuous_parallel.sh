#!/bin/bash

# Continuous Parallel Processing
# Runs 5 instances, each processing one page at a time continuously

cd /workspace/althen-rag-system

echo "🚀 Starting CONTINUOUS PARALLEL processing..."
echo "🔥 Maximum 5 pages processing simultaneously on RTX 4090"
echo "⚡ Each instance: grab page → process → grab next → repeat"
echo "📊 Continuous processing with no batch delays"
echo "Press Ctrl+C to stop ALL instances"
echo ""

# Trap Ctrl+C to kill all background processes
trap 'echo "🛑 Stopping all instances..."; kill $(jobs -p) 2>/dev/null; exit' INT

# Function to continuously process single pages
run_continuous_instance() {
    local instance_id=$1
    local page_counter=1
    
    while true; do
        echo "[Instance $instance_id] 🔍 Looking for next page to process..."
        
        # Run single page processing and capture output
        result=$(python3 scripts/process_single_page.py 2>&1)
        
        # Check if we got a page to process
        if echo "$result" | grep -q "No unprocessed pages found"; then
            echo "[Instance $instance_id] ⏸️  No pages available, waiting 30 seconds..."
            sleep 30
            continue
        elif echo "$result" | grep -q "Processing page"; then
            # Extract page ID from output
            page_id=$(echo "$result" | grep -o "Processing page [0-9]*" | grep -o "[0-9]*")
            echo "[Instance $instance_id] 📄 Processing page $page_id (#${page_counter})..."
            
            # Log detailed results
            echo "=== Page $page_id - $(date) ===" >> logs/instance_${instance_id}_continuous.log
            echo "$result" >> logs/instance_${instance_id}_continuous.log
            echo "" >> logs/instance_${instance_id}_continuous.log
            
            # Check if successful
            if echo "$result" | grep -q "SUCCESS!"; then
                echo "[Instance $instance_id] ✅ Page $page_id completed successfully"
            else
                echo "[Instance $instance_id] ❌ Page $page_id failed"
            fi
            
            page_counter=$((page_counter + 1))
        else
            echo "[Instance $instance_id] ⚠️  Unexpected result, waiting 10 seconds..."
            sleep 10
        fi
        
        # Small delay to prevent overwhelming the system
        sleep 2
    done
}

# Create single page processing script
cat > scripts/process_single_page.py << 'EOF'
#!/usr/bin/env python3
"""
Process a single page continuously - modified version of batch script
"""
import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.raganything_api_service import get_supabase_client, logger

async def get_single_unprocessed_page():
    """Get one unprocessed page and mark as processing immediately"""
    try:
        supabase = get_supabase_client()
        
        # Get one unprocessed page
        query = supabase.table("new_pages_index")\
            .select("*")\
            .or_("rag_ingestion_status.eq.not_started,rag_ingestion_status.is.null")\
            .limit(1)
        
        response = query.execute()
        pages = response.data if response.data else []
        
        if not pages:
            print("No unprocessed pages found")
            return None
            
        page = pages[0]
        
        # Immediately mark as processing to prevent conflicts
        supabase.table("new_pages_index").update({
            "rag_ingestion_status": "processing"
        }).eq("id", page['id']).execute()
        
        logger.info(f"Grabbed and marked page {page['id']} as processing")
        return page
        
    except Exception as e:
        logger.error(f"Error fetching unprocessed page: {e}")
        return None

async def process_single_page():
    """Process a single page"""
    from scripts.process_enhance_alt_text import process_page_enhance_alt_text
    
    # Get one page
    page = await get_single_unprocessed_page()
    
    if not page:
        return {"success": False, "error": "No pages available"}
    
    try:
        print(f"Processing page {page['id']}: {page['url'][:50]}...")
        result = await process_page_enhance_alt_text(page['id'])
        
        if result['success']:
            print(f"✅ Successfully processed page {page['id']}")
            print(f"   - Content length: {result.get('content_length', 0):,} chars")
            print(f"   - Images uploaded: {result.get('images_uploaded', 0)}")
            print(f"   - Datasheets: {result.get('datasheets_processed', 0)}")
            return {"success": True, "page_id": page['id']}
        else:
            print(f"❌ Failed to process page {page['id']}: {result.get('error')}")
            return {"success": False, "page_id": page['id'], "error": result.get('error')}
            
    except Exception as e:
        print(f"Error processing page {page['id']}: {e}")
        return {"success": False, "page_id": page['id'], "error": str(e)}

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Process one page
    result = asyncio.run(process_single_page())
    
    if result["success"]:
        print("SUCCESS!")
    else:
        print(f"FAILED: {result.get('error', 'Unknown error')}")
EOF

chmod +x scripts/process_single_page.py

# Start 5 instances with 10-second delays to avoid initial conflicts
echo "🔸 Starting Instance 1..."
run_continuous_instance 1 &

echo "⏳ Waiting 10 seconds before starting Instance 2..."
sleep 10
echo "🔸 Starting Instance 2..."
run_continuous_instance 2 &

echo "⏳ Waiting 10 seconds before starting Instance 3..."
sleep 10
echo "🔸 Starting Instance 3..."
run_continuous_instance 3 &

echo "⏳ Waiting 10 seconds before starting Instance 4..."
sleep 10
echo "🔸 Starting Instance 4..."
run_continuous_instance 4 &

echo "⏳ Waiting 10 seconds before starting Instance 5..."
sleep 10
echo "🔸 Starting Instance 5..."
run_continuous_instance 5 &

echo ""
echo "✅ All 5 instances started!"
echo ""
echo "📝 Monitor detailed logs with:"
echo "   tail -f logs/instance_*_continuous.log"
echo ""
echo "🛑 Press Ctrl+C to stop all instances"
echo ""

# Wait for all background jobs
wait