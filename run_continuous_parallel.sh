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
        # Get a single unprocessed page ID from database
        page_id=$(python3 -c "
import sys
sys.path.insert(0, '.')
from scripts.raganything_api_service import get_supabase_client
try:
    supabase = get_supabase_client()
    response = supabase.table('new_pages_index').select('id').or_('rag_ingestion_status.eq.not_started,rag_ingestion_status.is.null').limit(1).execute()
    if response.data:
        print(response.data[0]['id'])
    else:
        print('NO_PAGES')
except Exception as e:
    print('ERROR')
")
        
        if [ "$page_id" = "NO_PAGES" ]; then
            echo "[Instance $instance_id] ⏸️  No pages available, waiting 30 seconds..."
            sleep 30
            continue
        elif [ "$page_id" = "ERROR" ]; then
            echo "[Instance $instance_id] ❌ Database error, waiting 10 seconds..."
            sleep 10
            continue
        fi
        
        echo "[Instance $instance_id] 📄 Processing page $page_id (#${page_counter})..."
        
        # Run the final processing script (WITHOUT LightRAG upload)
        if python3 scripts/process_final_before_lightrag.py $page_id >> logs/instance_${instance_id}_continuous.log 2>&1; then
            echo "[Instance $instance_id] ✅ Page $page_id completed successfully"
        else
            echo "[Instance $instance_id] ❌ Page $page_id failed"
        fi
        
        page_counter=$((page_counter + 1))
        
        # Small delay to prevent overwhelming the system
        sleep 2
    done
}

# No need to create additional scripts - we use the existing working one

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