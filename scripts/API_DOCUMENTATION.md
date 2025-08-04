# RAG API Service Documentation

## Overview

The RAG API Service provides HTTP endpoints for processing pages through the complete RAGAnything pipeline:
- Web content scraping
- PDF processing with MinerU
- Image upload to Supabase Storage  
- Content ingestion to LightRAG

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements_api.txt
```

### 2. Configure Environment

Copy `.env.api.example` to `.env` and update the values:

```bash
cp .env.api.example .env
```

Key settings:
- `RAG_API_KEY`: Your secure API key for authentication
- `LIGHTRAG_SERVER_URL`: Your LightRAG server URL
- `SUPABASE_URL` & `SUPABASE_ANON_KEY`: Supabase configuration

### 3. Start the Service

```bash
python scripts/rag_api_service.py
```

The service will start on `http://localhost:8080`

## API Endpoints

### Health Check
```http
GET /health
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-31T12:00:00",
  "lightrag_connected": true,
  "version": "1.0.0"
}
```

### Process Single Page
```http
POST /process-page
Authorization: Bearer your-api-key-here
Content-Type: application/json

{
  "page_id": 9066,
  "fast_mode": true,
  "force_reprocess": false
}
```

Response:
```json
{
  "success": true,
  "page_id": 9066,
  "message": "Page 9066 processed successfully",
  "processing_time": 45.2,
  "results": {
    "processed": 1,
    "successful": 1,
    "datasheets_processed": 3,
    "multimodal_extractions": 12,
    "extraction_method": "RAGAnything_MinerU_Multimodal"
  }
}
```

### Check Page Status
```http
GET /status/9066
Authorization: Bearer your-api-key-here
```

Response:
```json
{
  "page_id": 9066,
  "status": "ingested",
  "details": {
    "url": "https://www.althencontrols.com/...",
    "created_at": "2024-01-31T10:00:00",
    "ingested": true
  }
}
```

### Batch Processing
```http
POST /batch-process
Authorization: Bearer your-api-key-here
Content-Type: application/json

{
  "page_ids": [9066, 9067, 9074],
  "fast_mode": true
}
```

## CRON Job Integration

### Example CRON Job Script

```bash
#!/bin/bash
# process_pending_pages.sh

API_URL="http://localhost:8080"
API_KEY="your-api-key-here"

# Get pending page IDs (customize this query)
PAGE_IDS=(9066 9067 9074)

# Process each page
for page_id in "${PAGE_IDS[@]}"; do
    echo "Processing page $page_id..."
    
    curl -X POST "$API_URL/process-page" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"page_id\": $page_id, \"fast_mode\": true}" \
        --max-time 300
    
    echo "Page $page_id completed"
    sleep 5
done
```

### Python CRON Job Example

```python
import requests
import time

API_URL = "http://localhost:8080"
API_KEY = "your-api-key-here"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def process_page(page_id):
    """Process a single page"""
    response = requests.post(
        f"{API_URL}/process-page",
        headers=HEADERS,
        json={
            "page_id": page_id,
            "fast_mode": True
        },
        timeout=300
    )
    return response.json()

def process_batch(page_ids):
    """Process multiple pages"""
    response = requests.post(
        f"{API_URL}/batch-process", 
        headers=HEADERS,
        json=page_ids,
        timeout=600
    )
    return response.json()

# Example usage
if __name__ == "__main__":
    # Process specific pages
    pages_to_process = [9066, 9067, 9074]
    
    for page_id in pages_to_process:
        print(f"Processing page {page_id}...")
        result = process_page(page_id)
        print(f"Result: {result['success']}")
        time.sleep(5)
```

## Cloud Deployment

### Docker Deployment

```bash
# Build the image
docker build -f Dockerfile.api -t rag-api-service .

# Run locally
docker run -p 8080:8080 --env-file .env rag-api-service

# Run in cloud (example)
docker run -d \
  -p 8080:8080 \
  -e RAG_API_KEY="your-secure-key" \
  -e LIGHTRAG_SERVER_URL="https://your-lightrag.com" \
  -e SUPABASE_URL="https://your-project.supabase.co" \
  -e SUPABASE_ANON_KEY="your-key" \
  rag-api-service
```

### Cloud Platform Examples

#### Google Cloud Run
```bash
# Deploy to Cloud Run
gcloud run deploy rag-api-service \
  --image gcr.io/your-project/rag-api-service \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 4Gi \
  --cpu 2 \
  --timeout 900
```

#### AWS ECS / Fargate
```json
{
  "family": "rag-api-service",
  "cpu": "2048",
  "memory": "4096",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "containerDefinitions": [{
    "name": "rag-api",
    "image": "your-registry/rag-api-service",
    "portMappings": [{"containerPort": 8080}],
    "environment": [
      {"name": "RAG_API_KEY", "value": "your-key"},
      {"name": "LIGHTRAG_SERVER_URL", "value": "https://your-lightrag.com"}
    ]
  }]
}
```

## Security

### API Key Authentication
- Set `RAG_API_KEY` environment variable
- Include in requests: `Authorization: Bearer your-api-key`
- Use strong, unique keys in production

### Rate Limiting (Production)
Consider adding rate limiting middleware:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/process-page")
@limiter.limit("10/minute")
async def process_page(request: Request, ...):
    ...
```

## Monitoring

### Health Checks
- Use `/health` endpoint for monitoring
- Check `lightrag_connected` status
- Monitor response times

### Logging
- Service logs to stdout (good for containers)
- Use structured logging for production
- Monitor processing times and success rates

### Metrics (Optional)
Add Prometheus metrics:

```python
from prometheus_client import Counter, Histogram, generate_latest

processed_pages = Counter('rag_pages_processed_total', 'Total processed pages')
processing_time = Histogram('rag_processing_duration_seconds', 'Processing duration')
```

## Troubleshooting

### Common Issues

1. **503 Service Unavailable**
   - Check LightRAG server connection
   - Verify environment variables

2. **401 Unauthorized**
   - Check API key in `Authorization` header
   - Verify `RAG_API_KEY` environment variable

3. **Slow Processing**
   - Use `fast_mode: true` for faster processing
   - Consider cloud deployment with better GPU

4. **Memory Issues**
   - Increase container memory limits
   - Use `fast_mode` to reduce memory usage
   - Process pages in smaller batches

### Debug Mode
Set environment variable for detailed logging:
```bash
export LOG_LEVEL=DEBUG
```

## OpenAPI Documentation

When the service is running, visit:
- **Swagger UI**: `http://localhost:8080/docs`
- **ReDoc**: `http://localhost:8080/redoc`
- **OpenAPI JSON**: `http://localhost:8080/openapi.json`