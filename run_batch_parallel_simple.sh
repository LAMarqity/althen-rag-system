#!/bin/bash

# Simple Parallel Batch Processing Script
# Runs 3 instances of the existing batch script in parallel

cd /workspace/althen-rag-system

echo "🚀 Starting PARALLEL batch processing (Simple Version)..."
echo "🔥 Running 3 concurrent processes on RTX 4090"
echo "📊 Processing 30 documents total (3 x 10) every 5 minutes"
echo "Press Ctrl+C to stop ALL processes"
echo ""

# Trap Ctrl+C to kill all background processes
trap 'echo "🛑 Stopping all workers..."; kill $(jobs -p) 2>/dev/null; exit' INT

# Function to run batch in a loop
run_worker() {
    local worker_id=$1
    while true; do
        echo "[Worker $worker_id] 🕐 $(date): Starting batch..."
        python3 scripts/batch_process_pages.py 2>&1 | sed "s/^/[Worker $worker_id] /" | tee -a logs/parallel_worker_${worker_id}.log
        echo "[Worker $worker_id] ✅ Complete. Waiting 5 minutes..."
        sleep 300
    done
}

# Start 3 workers with delays to avoid conflicts
echo "🔸 Starting Worker 1..."
run_worker 1 &
sleep 5

echo "🔸 Starting Worker 2..."
run_worker 2 &
sleep 5

echo "🔸 Starting Worker 3..."
run_worker 3 &

echo ""
echo "✅ All 3 workers started!"
echo ""
echo "📝 Monitor logs with:"
echo "   tail -f logs/parallel_worker_*.log"
echo ""
echo "🛑 Press Ctrl+C to stop all workers"
echo ""

# Wait for all background jobs
wait