#!/usr/bin/env python3
"""Simple API starter without Unicode output"""
import os
import sys
import uvicorn
from pathlib import Path

# Change to scripts directory
script_dir = Path(__file__).parent
os.chdir(script_dir.parent)  # Go to project root

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("Environment variables loaded")
except ImportError:
    print("Warning: python-dotenv not available")

# Get configuration
host = os.getenv("RAG_API_HOST", "0.0.0.0")
port = int(os.getenv("RAG_API_PORT", "8080"))

print(f"Starting API service on {host}:{port}")
print(f"LightRAG Server: {os.getenv('LIGHTRAG_SERVER_URL', 'Not set')}")
print(f"API Docs will be available at: http://localhost:{port}/docs")

# Add scripts to path
sys.path.insert(0, str(script_dir))

# Start the service
uvicorn.run(
    "rag_api_service:app",
    host=host,
    port=port,
    reload=False,
    log_level="info"
)