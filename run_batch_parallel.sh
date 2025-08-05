#!/bin/bash

# Parallel Batch Processing Script
# Runs 3 batch processes in parallel to maximize GPU usage

cd /workspace/althen-rag-system

echo "🚀 Starting PARALLEL batch processing..."
echo "🔥 Running 3 concurrent processes on RTX 4090"
echo "📊 Processing 30 documents total (3 x 10) every 5 minutes"
echo "Press Ctrl+C to stop ALL processes"
echo ""

# Function to run a single batch process
run_batch_worker() {
    local worker_id=$1
    while true; do
        echo "[Worker $worker_id] 🕐 $(date): Starting batch processing..."
        python3 scripts/batch_process_pages.py 2>&1 | sed "s/^/[Worker $worker_id] /" | tee -a logs/cron_batch_worker_${worker_id}.log
        echo "[Worker $worker_id] ✅ Batch complete. Waiting 5 minutes..."
        sleep 300
    done
}

# Trap Ctrl+C to kill all background processes
trap 'echo "🛑 Stopping all workers..."; kill $(jobs -p); exit' INT

# Start 3 workers in background
echo "🔸 Starting Worker 1..."
run_batch_worker 1 &

echo "🔸 Starting Worker 2..."
sleep 10  # Small delay to avoid conflicts
run_batch_worker 2 &

echo "🔸 Starting Worker 3..."
sleep 10  # Small delay to avoid conflicts
run_batch_worker 3 &

echo ""
echo "✅ All 3 workers started!"
echo "📝 Logs are in:"
echo "   - logs/cron_batch_worker_1.log"
echo "   - logs/cron_batch_worker_2.log"
echo "   - logs/cron_batch_worker_3.log"
echo ""
echo "💡 Monitor combined logs with: tail -f logs/cron_batch_worker_*.log"
echo ""

# Wait for all background jobs
wait