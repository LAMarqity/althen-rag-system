# RAGAnything GPU Setup Guide

## Overview
This guide provides instructions for deploying the Althen RAG System using RAGAnything on vast.ai GPU servers with CUDA support.

## System Architecture

### Components
1. **RAGAnything** - Multimodal document processing engine
2. **LightRAG** - Knowledge graph construction and retrieval
3. **MinerU** - Document parsing with GPU acceleration
4. **Supabase** - Cloud storage for documents and metadata
5. **N8N** - Workflow automation for batch processing
6. **vast.ai** - GPU compute infrastructure

## Prerequisites

### Local Development
- Python 3.10+
- Git
- Docker (for testing)
- Supabase account with API keys
- vast.ai account

### GPU Server Requirements
- NVIDIA GPU with CUDA 11.8+
- Minimum 16GB GPU memory (24GB+ recommended)
- Ubuntu 20.04 or 22.04
- 50GB+ storage for models and processing

## Installation Steps

### 1. Local Setup
```bash
# Clone repository
git clone https://github.com/LAMarqity/althen-rag-system.git
cd althen-rag-system

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements_cuda.txt
```

### 2. Configuration
Create `.env` file:
```env
# Supabase Configuration
SUPABASE_URL=your-supabase-url
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key

# OpenAI Configuration
OPENAI_API_KEY=your-openai-key
OPENAI_BASE_URL=https://api.openai.com/v1  # Optional

# RAGAnything Configuration
WORKING_DIR=/workspace/knowledge_base
PARSER=mineru
PARSE_METHOD=auto
DEVICE=cuda:0
ENABLE_IMAGE_PROCESSING=true
ENABLE_TABLE_PROCESSING=true
ENABLE_EQUATION_PROCESSING=true

# API Configuration
RAG_API_KEY=your-secure-api-key
API_HOST=0.0.0.0
API_PORT=8000

# Storage Configuration
USE_SUPABASE_STORAGE=true
LOCAL_STORAGE_PATH=/workspace/temp_storage
```

### 3. vast.ai Deployment

#### Create Instance
1. Go to [vast.ai](https://vast.ai/)
2. Select NVIDIA CUDA template
3. Choose GPU with minimum 16GB memory
4. Set disk space to 50GB+
5. Configure ports: 8000 (API), 8888 (Jupyter)

#### Environment Variables for vast.ai
```bash
PROVISIONING_SCRIPT=https://raw.githubusercontent.com/LAMarqity/althen-rag-system/main/scripts/vast_setup.sh
ENABLE_HTTPS=false
WORKSPACE=/workspace
```

### 4. API Endpoints

The system exposes the following endpoints:

- `POST /api/process/page` - Process single page from new_pages_index
- `POST /api/process/batch` - Process multiple pages
- `POST /api/query` - Query the knowledge base
- `GET /api/status/{job_id}` - Check processing status
- `GET /api/health` - Health check

### 5. N8N Integration

Configure N8N webhook to trigger processing:
```json
{
  "endpoint": "https://your-vast-instance.com/api/process/page",
  "headers": {
    "Authorization": "Bearer YOUR_RAG_API_KEY",
    "Content-Type": "application/json"
  },
  "body": {
    "page_id": "{{$node.Supabase.json.id}}",
    "process_datasheets": true,
    "store_in_supabase": true
  }
}
```

## Processing Workflow

1. N8N triggers processing with page_id
2. System fetches page from new_pages_index
3. Related datasheets fetched from new_datasheets_index
4. Documents processed using MinerU with GPU acceleration
5. Multimodal content extracted (text, images, tables, equations)
6. Knowledge graph built using LightRAG
7. Processed files stored in Supabase storage
8. Metadata updated in database

## GPU Optimization

### CUDA Configuration
```python
# Automatically detect and use GPU
import torch
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# For MinerU
mineru_config = {
    "device": "cuda:0",
    "backend": "pipeline",
    "formula": True,
    "table": True
}
```

### Memory Management
- Process documents in batches
- Clear GPU cache between large documents
- Use mixed precision when possible

## Monitoring

### Logs
- API logs: `/workspace/logs/api.log`
- Processing logs: `/workspace/logs/processing.log`
- GPU usage: `nvidia-smi -l 1`

### Metrics
- Processing time per document
- GPU memory usage
- API response times
- Storage usage in Supabase

## Troubleshooting

### Common Issues

1. **CUDA Out of Memory**
   - Reduce batch size
   - Process smaller documents
   - Clear GPU cache: `torch.cuda.empty_cache()`

2. **MinerU Installation**
   - Ensure LibreOffice installed: `apt-get install libreoffice`
   - Check CUDA version: `nvcc --version`

3. **Supabase Connection**
   - Verify API keys
   - Check network connectivity
   - Ensure storage bucket exists

## Security Considerations

1. Use environment variables for secrets
2. Enable HTTPS in production
3. Implement rate limiting
4. Rotate API keys regularly
5. Monitor access logs

## Backup and Recovery

1. Regular Supabase backups
2. Export knowledge graphs periodically
3. Version control for code changes
4. Document processing logs retention

## Support

For issues or questions:
- GitHub Issues: https://github.com/LAMarqity/althen-rag-system/issues
- Documentation: /docs
- Logs: Check `/workspace/logs/` for detailed error messages