-- Find pages with multiple datasheets (2 or more PDFs)
-- This query shows parent URLs that have 2+ datasheets for testing multi-PDF processing

SELECT 
    parent_url,
    COUNT(*) as datasheet_count,
    -- Get the page_id from new_pages_index 
    (SELECT id FROM new_pages_index WHERE url = parent_url LIMIT 1) as page_id,
    -- Show some example datasheet URLs
    STRING_AGG(url, ' | ') as datasheet_urls
FROM new_datasheets_index 
WHERE parent_url IS NOT NULL
GROUP BY parent_url
HAVING COUNT(*) >= 2
ORDER BY datasheet_count DESC, parent_url;

-- Alternative query: Show specific pages with their datasheets for easy testing
SELECT 
    p.id as page_id,
    p.url as page_url,
    p.category,
    p.subcategory,
    COUNT(d.id) as datasheet_count,
    p.ingested as already_processed
FROM new_pages_index p
JOIN new_datasheets_index d ON d.parent_url = p.url
GROUP BY p.id, p.url, p.category, p.subcategory, p.ingested
HAVING COUNT(d.id) >= 2
ORDER BY datasheet_count DESC, p.id;

-- Quick query to get just page IDs with multiple datasheets (for easy copy-paste)
SELECT 
    (SELECT id FROM new_pages_index WHERE url = parent_url LIMIT 1) as page_id,
    COUNT(*) as pdf_count
FROM new_datasheets_index 
WHERE parent_url IS NOT NULL
GROUP BY parent_url
HAVING COUNT(*) >= 2
ORDER BY pdf_count DESC
LIMIT 10;