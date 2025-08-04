#!/bin/bash

# Batch processing script for cron
# Runs the RAG processing on unprocessed pages

# Set working directory
cd /workspace/althen-rag-system || exit 1

# Use the Python from the venv directly (no need to activate)
PYTHON_PATH="/venv/main/bin/python"

# Fallback to system python if venv not available
if [ ! -f "$PYTHON_PATH" ]; then
    PYTHON_PATH="python"
fi

# Set environment variables (load from .env if exists)
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Add timestamp to log
echo "===========================================" >> cron.log
echo "Starting batch at $(date)" >> cron.log

# Run the batch processing
$PYTHON_PATH scripts/batch_process_pages.py >> cron.log 2>&1

# Check exit status
if [ $? -eq 0 ]; then
    echo "Batch completed successfully at $(date)" >> cron.log
else
    echo "Batch failed at $(date)" >> cron.log
fi

echo "===========================================" >> cron.log