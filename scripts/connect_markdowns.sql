-- Connect existing markdown files to new_pages_index table
-- This script adds markdown file paths and metadata to pages that have been processed

-- First, let's see what pages exist and their current status
SELECT 
    id,
    url,
    category,
    subcategory,
    rag_ingested,
    rag_ingestion_status,
    rag_ingested_at
FROM new_pages_index 
WHERE id IN (9067, 9064, 9063, 9066, 8983) -- Known page IDs from markdown files
ORDER BY id;

-- Add columns for markdown file connections if they don't exist
-- (Run these ALTER statements one by one if the columns don't exist)

-- ALTER TABLE new_pages_index ADD COLUMN IF NOT EXISTS markdown_file_path TEXT;
-- ALTER TABLE new_pages_index ADD COLUMN IF NOT EXISTS markdown_storage_url TEXT;
-- ALTER TABLE new_pages_index ADD COLUMN IF NOT EXISTS markdown_uploaded_at TIMESTAMPTZ;
-- ALTER TABLE new_pages_index ADD COLUMN IF NOT EXISTS markdown_file_size INTEGER;

-- Update pages with their markdown file information
-- Page 9067 - PT series string pots
UPDATE new_pages_index 
SET 
    markdown_file_path = 'knowledge_base/page_9067/pt1232-series-string-pot-en/auto/pt1232-series-string-pot-en.md',
    markdown_uploaded_at = NOW(),
    rag_ingested = true,
    rag_ingestion_status = 'completed',
    rag_ingested_at = NOW()
WHERE id = 9067;

-- Page 9064 - FDMM string pot
UPDATE new_pages_index 
SET 
    markdown_file_path = 'scripts/knowledge_base/page_9064/fdmm-string-pot-en/auto/fdmm-string-pot-en.md',
    markdown_uploaded_at = NOW(),
    rag_ingested = true,
    rag_ingestion_status = 'completed',
    rag_ingested_at = NOW()
WHERE id = 9064;

-- Page 9063 - FDMK120 analogue string pot
UPDATE new_pages_index 
SET 
    markdown_file_path = 'scripts/knowledge_base/page_9063/fdmk120-analogue-string-pot-en/auto/fdmk120-analogue-string-pot-en.md',
    markdown_uploaded_at = NOW(),
    rag_ingested = true,
    rag_ingestion_status = 'completed',
    rag_ingested_at = NOW()
WHERE id = 9063;

-- Page 9066 - PT8 series string pot
UPDATE new_pages_index 
SET 
    markdown_file_path = 'scripts/knowledge_base/page_9066/pt8-series-string-pot-pt8150-en/auto/pt8-series-string-pot-pt8150-en.md',
    markdown_uploaded_at = NOW(),
    rag_ingested = true,
    rag_ingestion_status = 'completed',
    rag_ingested_at = NOW()
WHERE id = 9066;

-- Page 8983 - MRI40A incremental encoder
UPDATE new_pages_index 
SET 
    markdown_file_path = 'scripts/knowledge_base/page_8983/mri40a-incremental-encoder-althen-sensors-controls/auto/mri40a-incremental-encoder-althen-sensors-controls.md',
    markdown_uploaded_at = NOW(),
    rag_ingested = true,
    rag_ingestion_status = 'completed',
    rag_ingested_at = NOW()
WHERE id = 8983;

-- Verify the updates
SELECT 
    id,
    url,
    category,
    subcategory,
    rag_ingested,
    rag_ingestion_status,
    markdown_file_path,
    markdown_uploaded_at
FROM new_pages_index 
WHERE markdown_file_path IS NOT NULL
ORDER BY id;

-- Query to see all pages that now have markdown connections
SELECT 
    COUNT(*) as total_pages_with_markdown,
    COUNT(CASE WHEN rag_ingestion_status = 'completed' THEN 1 END) as completed_pages,
    COUNT(CASE WHEN rag_ingested = true THEN 1 END) as ingested_pages
FROM new_pages_index 
WHERE markdown_file_path IS NOT NULL;