# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

### Running the System
```bash
# Start the main RAG system
python start.py

# Process pages with limited scope for testing
python start.py batch --max-pages 3 --max-datasheets 5

# Query the knowledge base
python start.py query "What sensors are available for temperature measurement?"

# View statistics
python start.py stats

# List unprocessed pages
python start.py list --limit 5
```

### API Service Commands
```bash
# Install API dependencies
pip install -r scripts/requirements_api.txt

# Start the API service
python scripts/rag_api_service.py

# Start API with uvicorn (for development)
python scripts/start_api.py
```

### Testing Commands
```bash
# Test Supabase connection
python start.py test

# Reset pages for testing
python start.py reset --limit 3

# Test API client
python scripts/test_api_client.py
```

## High-Level Architecture

### Core Components

1. **Main Entry Point** (`start.py`)
   - Validates environment setup
   - Loads .env configuration
   - Routes to async main function in `althen_rag_service.py`

2. **RAG Service** (`scripts/althen_rag_service.py`)
   - Integrates with Supabase to fetch pages and datasheets
   - Processes web content and PDFs using MinerU
   - Manages ingestion status tracking
   - Provides CLI interface for various operations

3. **API Service** (`scripts/rag_api_service.py`)
   - FastAPI-based HTTP service
   - Provides endpoints for page processing
   - Integrates with LightRAG server
   - Handles authentication via API keys

4. **Knowledge Processing**
   - Uses RAGAnything for document processing
   - Creates vector embeddings with OpenAI
   - Builds knowledge graphs with entities and relationships
   - Supports multiple query modes (hybrid, local, global, naive)

### Data Flow
1. Pages and datasheets are fetched from Supabase tables:
   - `new_pages_index` - Web pages to process
   - `new_datasheets_index` - PDF datasheets linked to pages

2. Content is processed through:
   - Web scraping with BeautifulSoup
   - PDF extraction with MinerU (limited to 10 pages for efficiency)
   - Text chunking and embedding generation

3. Processed data is stored in:
   - `./knowledge_base/` - Local RAG storage
   - Supabase storage - For images and processed documents
   - Knowledge graphs - Entities and relationships

### Environment Configuration
Essential environment variables:
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_ANON_KEY` - Supabase anonymous key
- `OPENAI_API_KEY` - For embeddings and LLM processing
- `WORKING_DIR` - Storage directory (default: ./knowledge_base)
- `RAG_API_KEY` - For API authentication
- `LIGHTRAG_SERVER_URL` - LightRAG server endpoint

### Key Limitations
- PDF processing limited to 10 pages per document
- Web content truncated at 3000 characters
- Requires LibreOffice for PDF processing
- Windows users need specific MinerU setup