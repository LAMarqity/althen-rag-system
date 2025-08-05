#!/bin/bash

# Five Parallel Batch Processing
# Runs 5 instances of the batch script in parallel

cd /workspace/althen-rag-system

echo "🚀 Starting FIVE PARALLEL batch processing..."
echo "🔥 Running 5 parallel instances on RTX 4090"
echo "📊 Up to 50 documents processing simultaneously (5 x 10)"
echo "⚡ Each instance: process 10 → wait 1min → repeat"
echo "Press Ctrl+C to stop ALL instances"
echo ""

# Trap Ctrl+C to kill all background processes
trap 'echo "🛑 Stopping all instances..."; kill $(jobs -p) 2>/dev/null; exit' INT

# Function to run batch processing in a loop
run_instance() {
    local instance_id=$1
    local batch_counter=1
    
    while true; do
        echo "[Instance $instance_id] 🕐 $(date): Starting batch #${batch_counter}..."
        
        # Initialize counters
        page_count=0
        success_count=0
        failed_count=0
        
        # Run batch with live progress tracking and error handling
        (
            python3 scripts/batch_process_pages.py 2>&1 || echo "BATCH_ERROR: Script failed"
        ) | while IFS= read -r line; do
            # Log everything to detailed file
            echo "$line" >> logs/instance_${instance_id}_detailed.log
            
            # Handle batch errors
            if echo "$line" | grep -q "BATCH_ERROR:"; then
                echo "[Instance $instance_id] ❌ Batch script failed, will retry in 1 minute..."
                break
            fi
            
            # Show progress for page processing
            if echo "$line" | grep -q "Processing page.*:"; then
                page_count=$((page_count + 1))
                echo "[Instance $instance_id] 📄 Processing page ${page_count}/10..."
            elif echo "$line" | grep -q "Successfully processed page"; then
                success_count=$((success_count + 1))
                echo "[Instance $instance_id] ✅ Page completed (${success_count} success so far)"
            elif echo "$line" | grep -q "Failed to process page"; then
                failed_count=$((failed_count + 1))
                echo "[Instance $instance_id] ❌ Page failed (${failed_count} failed so far)"
            elif echo "$line" | grep -q "Batch complete:"; then
                echo "[Instance $instance_id] ✅ Batch #${batch_counter} complete!"
            fi
        done
        
        echo "[Instance $instance_id] ⏳ Waiting 1 minute..."
        batch_counter=$((batch_counter + 1))
        sleep 60
    done
}

# Start 5 instances with 10-second delays to avoid conflicts
echo "🔸 Starting Instance 1..."
run_instance 1 &

echo "⏳ Waiting 10 seconds before starting Instance 2..."
sleep 10
echo "🔸 Starting Instance 2..."
run_instance 2 &

echo "⏳ Waiting 10 seconds before starting Instance 3..."
sleep 10
echo "🔸 Starting Instance 3..."
run_instance 3 &

echo "⏳ Waiting 10 seconds before starting Instance 4..."
sleep 10
echo "🔸 Starting Instance 4..."
run_instance 4 &

echo "⏳ Waiting 10 seconds before starting Instance 5..."
sleep 10
echo "🔸 Starting Instance 5..."
run_instance 5 &

echo ""
echo "✅ All 5 instances started!"
echo ""
echo "📝 Monitor detailed logs with:"
echo "   tail -f logs/instance_*_detailed.log"
echo ""
echo "🛑 Press Ctrl+C to stop all instances"
echo ""

# Wait for all background jobs
wait