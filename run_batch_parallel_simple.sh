#!/bin/bash

# Batch Processing Loop Script
# Runs single batch processing every 5 minutes

cd /workspace/althen-rag-system

echo "🚀 Starting batch processing loop..."
echo "🔥 Processing 10 documents every 1 minute on RTX 4090"
echo "📊 Reserving 10 pages at start, processing sequentially"
echo "Press Ctrl+C to stop"
echo ""

# Trap Ctrl+C to stop the process
trap 'echo "🛑 Stopping batch processing..."; exit' INT

while true; do
    echo "========================================="
    echo "🕐 $(date): Starting batch processing..."
    echo "========================================="
    
    # Run the batch processing script
    python3 scripts/batch_process_pages.py 2>&1 | tee -a logs/batch_processing.log
    
    echo ""
    echo "✅ $(date): Batch complete"
    echo "⏳ Waiting 1 minute for next batch..."
    echo "💡 Press Ctrl+C to stop"
    echo ""
    
    # Wait 1 minute (60 seconds)
    sleep 60
done