# Supabase Field Documentation

## Overview
This document clarifies the field usage in Supabase tables for tracking document processing status.

## Table: `new_pages_index`

### Current Fields:
- **`ingested`** (boolean) 
  - Simple processing flag
  - Used by: Basic processors, test scripts
  - Set to `true` when page content is uploaded to LightRAG
  
- **`rag_ingested`** (boolean)
  - Advanced RAG processing flag  
  - Used by: RAGAnything API service
  - Set to `true` when full RAG pipeline completes
  
- **`rag_ingested_at`** (timestamp)
  - Timestamp of RAG processing
  - Used by: RAGAnything API service
  - Format: ISO 8601 string
  
- **`processing_metadata`** (JSON)
  - Detailed processing results
  - Used by: RAGAnything API service
  - Contains: document counts, errors, processing details
  
- **`lightrag_track_id`** (string)
  - Async job tracking ID
  - Currently unused (always NULL)
  - Intended for: Background job tracking

## Table: `new_datasheets_index`

### Current Fields:
- **`ingested`** (boolean)
  - Simple processing flag
  - Used by: All processors
  - Set to `true` when PDF is processed

### Missing Fields (cause errors if used):
- ~~`ingested_at`~~ - Does NOT exist (don't use!)
- ~~`rag_ingested`~~ - Does NOT exist (don't use!)
- ~~`processing_metadata`~~ - Does NOT exist (don't use!)

## Recommended Usage Strategy

### For Simple Processing (LightRAG upload only):
```python
# When processing completes successfully:
supabase.table("new_pages_index").update({
    "ingested": True  # Simple flag only
}).eq("id", page_id).execute()

supabase.table("new_datasheets_index").update({
    "ingested": True  # Simple flag only
}).eq("id", datasheet_id).execute()
```

### For Advanced RAG Processing (with metadata):
```python
# When RAG processing completes:
supabase.table("new_pages_index").update({
    "ingested": True,  # For backward compatibility
    "rag_ingested": True,  # RAG-specific flag
    "rag_ingested_at": datetime.now().isoformat(),
    "processing_metadata": json.dumps({
        "processed_documents": [...],
        "content_length": 12345,
        "errors": [],
        "timestamp": datetime.now().isoformat()
    })
}).eq("id", page_id).execute()
```

## Query Patterns

### Find unprocessed pages (simple):
```sql
SELECT * FROM new_pages_index WHERE ingested = false
```

### Find unprocessed pages (RAG):
```sql
SELECT * FROM new_pages_index WHERE rag_ingested = false OR rag_ingested IS NULL
```

### Find pages processed but not RAG processed:
```sql
SELECT * FROM new_pages_index WHERE ingested = true AND (rag_ingested = false OR rag_ingested IS NULL)
```

### Find failed processing:
```sql
SELECT * FROM new_pages_index 
WHERE processing_metadata::jsonb->>'errors' != '[]'
```

## Migration Notes

To add missing columns to datasheets table (if needed):
```sql
-- Add timestamp tracking to datasheets
ALTER TABLE new_datasheets_index 
ADD COLUMN IF NOT EXISTS ingested_at TIMESTAMP WITH TIME ZONE;

-- Add RAG tracking to datasheets
ALTER TABLE new_datasheets_index 
ADD COLUMN IF NOT EXISTS rag_ingested BOOLEAN DEFAULT false;

-- Add metadata to datasheets
ALTER TABLE new_datasheets_index 
ADD COLUMN IF NOT EXISTS processing_metadata JSONB;
```

## Current Implementation Status

- ✅ `process_page.py` - Uses `ingested` only
- ✅ `process_page_enhanced.py` - Uses `ingested` only
- ✅ `test_page_9022_lightrag.py` - Uses `ingested` only
- ⚠️ `raganything_api_service.py` - Uses all RAG fields (advanced)
- ✅ `althen_rag_service.py` - Uses `ingested` only

## Recommendation

For consistency and simplicity:
1. Use `ingested` for basic "uploaded to LightRAG" tracking
2. Use `rag_ingested` + metadata for advanced RAG processing
3. Don't try to use fields that don't exist in the tables
4. Consider adding missing fields to datasheets table if needed