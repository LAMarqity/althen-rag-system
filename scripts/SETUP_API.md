# RAG API Service - Quick Setup Guide

## 🚀 Complete API Service for Page Processing

Your RAG API service is ready! This allows you to process pages via HTTP requests from CRON jobs or other applications.

## 📁 Files Created

```
scripts/
├── rag_api_service.py         # Main FastAPI service
├── start_api.py              # Startup script with checks
├── test_api_client.py        # Test client & CRON examples
├── requirements_api.txt      # Dependencies
├── .env.api.example         # Environment configuration
├── Dockerfile.api           # Docker deployment
├── API_DOCUMENTATION.md     # Full documentation
└── SETUP_API.md            # This setup guide
```

## ⚡ Quick Start (Local)

### 1. Install Dependencies
```bash
pip install fastapi uvicorn python-multipart
```

### 2. Configure Environment
```bash
cd scripts
cp .env.api.example .env
```

Edit `.env` with your actual values:
```env
RAG_API_KEY=your-secure-api-key-change-this
LIGHTRAG_SERVER_URL=https://lightrag-latest-hyhs.onrender.com/
LIGHTRAG_API_KEY=your-lightrag-api-key
SUPABASE_URL=https://titreaoasgbwzjsrlrne.supabase.co
SUPABASE_ANON_KEY=your-supabase-key
```

### 3. Start the Service
```bash
python start_api.py
```

Service will be available at:
- **API**: http://localhost:8080
- **Docs**: http://localhost:8080/docs
- **Health**: http://localhost:8080/health

## 🔧 API Usage

### Process a Single Page
```bash
curl -X POST "http://localhost:8080/process-page" \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"page_id": 9066, "fast_mode": true}'
```

### Check Page Status
```bash
curl -X GET "http://localhost:8080/status/9066" \
  -H "Authorization: Bearer your-api-key"
```

### Health Check
```bash
curl http://localhost:8080/health
```

## 🕒 CRON Job Integration

### Simple Bash Script
```bash
#!/bin/bash
# cron_process_pages.sh

API_URL="http://localhost:8080"
API_KEY="your-api-key"

# Process specific pages
for page_id in 9066 9067 9074; do
    echo "Processing page $page_id..."
    curl -X POST "$API_URL/process-page" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"page_id\": $page_id, \"fast_mode\": true}" \
        --max-time 300
    sleep 10
done
```

### Python CRON Job
Use the provided `test_api_client.py`:

```python
from test_api_client import RAGAPIClient

# Initialize client
client = RAGAPIClient("http://localhost:8080", "your-api-key")

# Process pages
pages = [9066, 9067, 9074]
for page_id in pages:
    result = client.process_page(page_id, fast_mode=True)
    print(f"Page {page_id}: {'✅' if result['success'] else '❌'}")
```

### CRON Schedule Example
```bash
# Add to crontab (crontab -e)
# Process pages every hour
0 * * * * /path/to/your/cron_process_pages.sh

# Process pages daily at 2 AM
0 2 * * * /usr/bin/python3 /path/to/your/cron_job.py
```

## ☁️ Cloud Deployment

### Option 1: Docker
```bash
# Build and run
docker build -f Dockerfile.api -t rag-api .
docker run -p 8080:8080 --env-file .env rag-api
```

### Option 2: Cloud Platforms

**Google Cloud Run**:
```bash
gcloud run deploy rag-api \
  --source . \
  --platform managed \
  --region us-central1 \
  --memory 4Gi --cpu 2
```

**AWS/Azure/DigitalOcean**: Use the Docker image

### GPU-Enabled Cloud Deployment
For better MinerU performance:

```yaml
# docker-compose.gpu.yml
version: '3.8'
services:
  rag-api:
    build:
      context: .
      dockerfile: Dockerfile.api
    ports:
      - "8080:8080"
    environment:
      - RAG_API_KEY=your-key
      - LIGHTRAG_SERVER_URL=https://your-lightrag.com
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

## 🧪 Testing

### 1. Test Client
```bash
python test_api_client.py
```

### 2. Manual Testing
Visit http://localhost:8080/docs for interactive API documentation

### 3. Health Check
```bash
curl http://localhost:8080/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-31T12:00:00",
  "lightrag_connected": true,
  "version": "1.0.0"
}
```

## 🔒 Security

### API Key Authentication
- Set a strong `RAG_API_KEY` in production
- Use HTTPS in production deployments
- Consider rate limiting for public deployments

### Production Recommendations
```env
# Strong API key
RAG_API_KEY=a-very-long-random-string-here

# Restrict host binding in production
RAG_API_HOST=127.0.0.1  # Local only

# Use HTTPS URLs
LIGHTRAG_SERVER_URL=https://your-lightrag.com
```

## 📊 Monitoring

### Built-in Endpoints
- `/health` - Service health
- `/` - Service info and endpoints

### Custom Monitoring
Add to your monitoring stack:
```bash
# Check if service is responding
curl -f http://localhost:8080/health || alert "RAG API Down"

# Check processing success rate
curl -s http://localhost:8080/metrics  # If you add metrics
```

## 🐛 Troubleshooting

### Common Issues

**503 Service Unavailable**
- Check LightRAG server connection
- Verify LIGHTRAG_SERVER_URL and API key

**401 Unauthorized**
- Check API key in Authorization header
- Verify RAG_API_KEY environment variable

**Slow Processing**
- Use `fast_mode: true`
- Deploy with GPU for MinerU acceleration
- Increase memory limits

**Port Already in Use**
```bash
# Find and kill process using port 8080
netstat -ano | findstr :8080
taskkill /PID <PID> /F

# Or use different port
export RAG_API_PORT=8081
```

### Debug Mode
```bash
export LOG_LEVEL=DEBUG
python rag_api_service.py
```

## 📈 Scaling

### Horizontal Scaling
- Deploy multiple instances behind load balancer
- Use different ports: 8080, 8081, 8082
- Share same LightRAG and Supabase backend

### Vertical Scaling
- Increase memory for MinerU processing
- Add GPU for faster PDF processing
- Use faster storage for knowledge_base

## 🔄 Next Steps

1. **Test locally**: Run the service and test with a few pages
2. **Configure CRON**: Set up automated processing
3. **Deploy to cloud**: For better GPU access
4. **Monitor**: Add health checks to your monitoring
5. **Scale**: Add more instances as needed

## 📞 Support

- **API Documentation**: http://localhost:8080/docs
- **Full Documentation**: `API_DOCUMENTATION.md`
- **Test Examples**: `test_api_client.py`

Your RAG API service is production-ready! 🎉