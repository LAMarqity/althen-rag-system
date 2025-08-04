# Deployment Guide for vast.ai GPU Server

## Quick Start

### 1. Push to GitHub

```bash
# Initialize git repository (if not already done)
git init

# Add GitHub remote
git remote add origin https://github.com/LAMarqity/althen-rag-system.git

# Add all files
git add .

# Commit
git commit -m "Initial commit: RAGAnything GPU setup for Althen RAG system"

# Push to GitHub
git push -u origin main
```

### 2. Create vast.ai Instance

1. Go to [vast.ai](https://vast.ai/)
2. Search for instances with:
   - GPU: RTX 3090/4090 or A100 (minimum 16GB VRAM)
   - Disk: 50GB+
   - CUDA: 11.8+
   - Docker: Yes

3. Click "RENT" on suitable instance

4. Configure instance:
   ```
   Image: nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04
   On-start script: wget -O - https://raw.githubusercontent.com/LAMarqity/althen-rag-system/main/scripts/vast_setup.sh | bash
   Jupyter: Enable
   SSH: Enable
   Ports: 8000,8888
   ```

5. Set environment variables:
   ```
   PROVISIONING_SCRIPT=https://raw.githubusercontent.com/LAMarqity/althen-rag-system/main/scripts/vast_setup.sh
   WORKSPACE=/workspace
   ENABLE_HTTPS=false
   ```

### 3. Connect to Instance

#### Via SSH:
```bash
# Get connection details from vast.ai dashboard
ssh -p [PORT] root@[HOST] -L 8000:localhost:8000
```

#### Via Jupyter:
Click "Open" → Jupyter in vast.ai dashboard

### 4. Configure API Keys

Once connected, edit the environment file:
```bash
cd /workspace/althen-rag-system
nano .env
```

Add your keys:
```env
SUPABASE_URL=your-supabase-url
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key
OPENAI_API_KEY=your-openai-key
RAG_API_KEY=your-secure-api-key
```

### 5. Start Services

```bash
# Start the API service
/workspace/start_services.sh

# Or manually:
cd /workspace/althen-rag-system
source venv/bin/activate
python scripts/raganything_api_service.py
```

### 6. Test the API

```bash
# Health check
curl http://localhost:8000/api/health

# GPU status
curl http://localhost:8000/api/gpu/status

# Process a page (requires API key)
curl -X POST http://localhost:8000/api/process/page \
  -H "Authorization: Bearer YOUR_RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"page_id": 9066, "process_datasheets": true}'
```

## N8N Integration

### Webhook Configuration

1. In N8N, create HTTP Request node:
```json
{
  "method": "POST",
  "url": "https://your-vast-instance.com/api/process/page",
  "authentication": "genericCredentialType",
  "genericAuthType": "httpHeaderAuth",
  "httpHeaderAuth": {
    "name": "Authorization",
    "value": "Bearer YOUR_RAG_API_KEY"
  },
  "sendBody": true,
  "bodyContentType": "json",
  "jsonBody": {
    "page_id": "={{ $json.id }}",
    "process_datasheets": true,
    "store_in_supabase": true
  }
}
```

2. Add trigger (Cron or Supabase webhook)

3. Connect to Supabase node to fetch pages

## Monitoring

### GPU Usage
```bash
# Real-time GPU monitoring
/workspace/monitor_gpu.sh

# Or use nvidia-smi
watch -n 1 nvidia-smi
```

### API Logs
```bash
# View API logs
tail -f /workspace/logs/raganything.out.log

# View error logs
tail -f /workspace/logs/raganything.err.log
```

### Service Status
```bash
# Check service status
supervisorctl status

# Restart service
supervisorctl restart raganything
```

## Optimization Tips

### GPU Memory Management

1. **Batch Processing**: Process documents in batches to optimize GPU usage
2. **Clear Cache**: Regularly clear GPU cache between large documents
3. **Mixed Precision**: Use fp16 for faster processing when possible

### Performance Tuning

```python
# In your .env file
BATCH_SIZE=4
MAX_WORKERS=2
GPU_MEMORY_FRACTION=0.8
ENABLE_MIXED_PRECISION=true
```

### Storage Optimization

1. **Temporary Files**: Clean up temp files after processing
2. **Supabase Storage**: Use for permanent storage only
3. **Local Cache**: Keep frequently accessed files locally

## Scaling

### Multiple GPUs
```python
# Configure for multi-GPU
CUDA_VISIBLE_DEVICES=0,1
DEVICE=cuda:0  # Primary GPU
```

### Load Balancing
Use multiple vast.ai instances with a load balancer:
1. Deploy multiple instances
2. Use nginx or HAProxy for load balancing
3. Share knowledge base via Supabase

## Cost Optimization

1. **Auto-shutdown**: Configure auto-shutdown when idle
2. **Spot Instances**: Use interruptible instances for batch processing
3. **Schedule Processing**: Run during off-peak hours

## Troubleshooting

### CUDA Not Available
```bash
# Check CUDA installation
nvcc --version
python -c "import torch; print(torch.cuda.is_available())"
```

### MinerU Issues
```bash
# Reinstall MinerU
pip uninstall magic-pdf mineru
pip install magic-pdf[full] --extra-index-url https://wheels.myhloli.com
```

### Supabase Connection
```bash
# Test Supabase connection
python -c "
from supabase import create_client
import os
client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_ANON_KEY'))
print('Connected!' if client else 'Failed')
"
```

## Security

### API Authentication
- Always use strong API keys
- Rotate keys regularly
- Use HTTPS in production

### Network Security
- Configure firewall rules
- Use VPN for sensitive data
- Monitor access logs

## Backup

### Knowledge Base Backup
```bash
# Backup to Supabase
python scripts/backup_to_supabase.py

# Local backup
tar -czf backup_$(date +%Y%m%d).tar.gz /workspace/knowledge_base
```

### Configuration Backup
```bash
# Backup configs
cp .env .env.backup
git add . && git commit -m "Config backup $(date +%Y%m%d)"
git push
```