#!/bin/bash
# vast.ai provisioning script for RAGAnything GPU setup

set -e  # Exit on error

echo "================================================"
echo "RAGAnything GPU Setup for vast.ai"
echo "================================================"

# Update system
echo "Updating system packages..."
apt-get update
apt-get upgrade -y

# Install additional dependencies
echo "Installing system dependencies..."
apt-get install -y \
    libreoffice \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    git \
    wget \
    curl \
    vim \
    htop \
    build-essential

# Clone repository
echo "Cloning RAGAnything repository..."
cd /workspace
if [ ! -d "althen-rag-system" ]; then
    git clone https://github.com/LAMarqity/althen-rag-system.git
fi
cd althen-rag-system

# Setup Python environment
echo "Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate

# Install PyTorch with CUDA
echo "Installing PyTorch with CUDA support..."
pip install --upgrade pip setuptools wheel
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install requirements
echo "Installing Python requirements..."
if [ -f "requirements_cuda.txt" ]; then
    pip install -r requirements_cuda.txt
else
    echo "Warning: requirements_cuda.txt not found, installing basic packages..."
    pip install raganything[all] lightrag mineru fastapi uvicorn supabase
fi

# Check GPU availability
echo "Checking GPU availability..."
python3 -c "
import torch
if torch.cuda.is_available():
    print(f'✅ GPU Available: {torch.cuda.get_device_name(0)}')
    print(f'   Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB')
    print(f'   CUDA Version: {torch.version.cuda}')
else:
    print('❌ No GPU detected!')
"

# Create necessary directories
echo "Creating directories..."
mkdir -p logs knowledge_base temp_storage processed_documents

# Setup environment file
echo "Setting up environment configuration..."
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo "Please edit .env file with your API keys"
fi

# Install supervisor for process management
echo "Installing supervisor..."
apt-get install -y supervisor

# Create supervisor config for API service
cat > /etc/supervisor/conf.d/raganything.conf <<EOL
[program:raganything]
command=/workspace/althen-rag-system/venv/bin/python /workspace/althen-rag-system/scripts/raganything_api_service.py
directory=/workspace/althen-rag-system
autostart=true
autorestart=true
stderr_logfile=/workspace/logs/raganything.err.log
stdout_logfile=/workspace/logs/raganything.out.log
environment=PATH="/workspace/althen-rag-system/venv/bin:%(ENV_PATH)s",PYTHONPATH="/workspace/althen-rag-system"
user=root
EOL

# Create startup script
cat > /workspace/start_services.sh <<'EOL'
#!/bin/bash
echo "Starting RAGAnything services..."

# Activate virtual environment
source /workspace/althen-rag-system/venv/bin/activate

# Check GPU
echo "GPU Status:"
nvidia-smi

# Start supervisor
service supervisor start
supervisorctl reread
supervisorctl update
supervisorctl start raganything

# Show service status
echo ""
echo "Service Status:"
supervisorctl status

# Show API endpoint
echo ""
echo "================================================"
echo "RAGAnything API is running at:"
echo "http://0.0.0.0:8000"
echo "API Docs: http://0.0.0.0:8000/docs"
echo "================================================"

# Keep container running
tail -f /workspace/logs/raganything.out.log
EOL

chmod +x /workspace/start_services.sh

# Install Jupyter for development
echo "Installing Jupyter..."
pip install jupyter jupyterlab ipywidgets

# Create Jupyter config
jupyter notebook --generate-config
cat >> ~/.jupyter/jupyter_notebook_config.py <<EOL
c.NotebookApp.ip = '0.0.0.0'
c.NotebookApp.port = 8888
c.NotebookApp.open_browser = False
c.NotebookApp.allow_root = True
c.NotebookApp.token = ''
c.NotebookApp.password = ''
EOL

# Install monitoring tools
echo "Installing monitoring tools..."
pip install gpustat py3nvml

# Create GPU monitoring script
cat > /workspace/monitor_gpu.sh <<'EOL'
#!/bin/bash
while true; do
    clear
    echo "================================================"
    echo "GPU Monitoring - $(date)"
    echo "================================================"
    nvidia-smi
    echo ""
    gpustat
    sleep 5
done
EOL
chmod +x /workspace/monitor_gpu.sh

# Final message
echo ""
echo "================================================"
echo "✅ Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Edit /workspace/althen-rag-system/.env with your API keys"
echo "2. Run: /workspace/start_services.sh"
echo "3. Access API at: http://0.0.0.0:8000"
echo "4. Access Jupyter at: http://0.0.0.0:8888"
echo ""
echo "Useful commands:"
echo "- Monitor GPU: /workspace/monitor_gpu.sh"
echo "- View logs: tail -f /workspace/logs/raganything.out.log"
echo "- Restart service: supervisorctl restart raganything"
echo "================================================"