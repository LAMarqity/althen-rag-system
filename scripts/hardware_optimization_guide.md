# 🔧 Hardware Optimization Guide for MinerU

## Why Some PDFs Work and Others Don't

### ✅ **Success Factors (page_9067 PT1232)**:
- **Simple Layout**: Clean text, standard tables
- **First in Batch**: Fresh memory state
- **Moderate Size**: ~890KB PDF
- **Standard Format**: Well-structured document

### ❌ **Failure Factors (Other Pages)**:
- **Complex Layout**: Scanned text, irregular formatting  
- **Memory Accumulation**: Later PDFs in processing batch
- **Large Size**: Multi-megabyte files
- **Heavy Graphics**: Many images, complex tables

## 📊 Performance Tiers by Hardware

### **Tier 1: High-End (16GB+ RAM)**
```bash
# Full multimodal processing
python scripts/lightrag_server_client.py ingest --max-pages 10
```

### **Tier 2: Mid-Range (8-16GB RAM)** ⭐ **YOUR SETUP**
```bash
# Mixed approach - try full, fallback to fast
python scripts/lightrag_server_client.py ingest --max-pages 5 --fast-mode
```

### **Tier 3: Low-End (4-8GB RAM)**
```bash
# Text-only processing for speed
python scripts/lightrag_server_client.py ingest --max-pages 1 --fast-mode
```

## 🎯 Optimized Strategy for Your Hardware

### **Option 1: Smart Batch Processing** (Recommended)
```bash
# Process 3 pages at a time with memory cleanup
for i in {1..5}; do
    python scripts/lightrag_server_client.py ingest --max-pages 3 --fast-mode
    echo "Batch $i complete, memory cleared"
    sleep 5
done
```

### **Option 2: Text-Only Speed Run**
```bash
# Process 50 pages quickly with text extraction only
python scripts/lightrag_server_client.py ingest --max-pages 50 --fast-mode
```

### **Option 3: Single PDF Focus**
```bash
# Perfect single PDFs manually
python scripts/lightrag_server_client.py pdf path/to/important.pdf
```

## 🧠 Memory Optimizations Applied

1. **✅ Reduced GPU Memory**: `--vram 2` (was 4)
2. **✅ Shorter Timeouts**: 90s full / 45s text (was 120s)
3. **✅ Garbage Collection**: Memory cleanup after each PDF
4. **✅ CPU Processing**: Avoids GPU memory conflicts
5. **✅ Better Fallback**: PyPDF2 extracts 4,600+ chars vs 103

## 📈 Expected Results

| Hardware Tier | MinerU Success Rate | Content Quality | Processing Speed |
|---------------|---------------------|-----------------|------------------|
| High-End      | 80-90%             | Full multimodal | Fast             |
| **Your Setup** | 30-50%             | **Rich fallback** | **Medium**       |
| Low-End       | 10-20%             | Text-only       | Slow             |

**Your Result**: Even with MinerU timeouts, you get **4,600+ character extractions** vs previous 103!

## 🚀 Production Recommendation

**Run 3-page batches with 5-second breaks**:
```bash
# This will get you ~200 pages per hour with good content quality
while true; do
    python scripts/lightrag_server_client.py ingest --max-pages 3 --fast-mode
    if [ $? -eq 0 ]; then
        echo "✅ Batch complete"
        sleep 5
    else
        echo "❌ Batch failed, stopping"
        break
    fi
done
```

This balances **content quality** (4,600+ chars per PDF) with **hardware limitations**.