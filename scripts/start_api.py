#!/usr/bin/env python3
"""
Startup script for RAG API Service
Handles environment loading and service initialization
"""

import os
import sys
import subprocess
from pathlib import Path

def load_environment():
    """Load environment variables from .env file"""
    env_file = Path(".env")
    
    if env_file.exists():
        print("✅ Loading environment from .env file")
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            print("⚠️ python-dotenv not available, install with: pip install python-dotenv")
            return False
    else:
        print("⚠️ No .env file found, using system environment variables")
        print("💡 Create .env from .env.api.example for local configuration")
    
    return True

def check_dependencies():
    """Check if required dependencies are installed"""
    required_packages = [
        "fastapi",
        "uvicorn",
        "supabase",
        "requests",
        "beautifulsoup4"
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("❌ Missing required packages:")
        for package in missing_packages:
            print(f"   - {package}")
        print("\n📦 Install missing packages with:")
        print("   pip install -r requirements_api.txt")
        return False
    
    print("✅ All required dependencies available")
    return True

def check_configuration():
    """Check critical configuration"""
    required_env_vars = [
        "LIGHTRAG_SERVER_URL",
        "SUPABASE_URL",
        "RAG_API_KEY"
    ]
    
    missing_vars = []
    
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print("⚠️ Missing environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n💡 Set these in your .env file or environment")
        return False
    
    print("✅ Configuration looks good")
    return True

def main():
    """Main startup function"""
    print("🚀 Starting RAG API Service...")
    print("=" * 50)
    
    # Change to scripts directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    print(f"📁 Working directory: {script_dir.absolute()}")
    
    # Load environment
    if not load_environment():
        sys.exit(1)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Check configuration
    if not check_configuration():
        print("\n⚠️ Configuration issues detected, but service will start anyway...")
        print("   Some features may not work properly")
    
    # Get configuration
    host = os.getenv("RAG_API_HOST", "0.0.0.0")
    port = int(os.getenv("RAG_API_PORT", "8080"))
    lightrag_url = os.getenv("LIGHTRAG_SERVER_URL", "Unknown")
    
    print("\n🔧 Service Configuration:")
    print(f"   Host: {host}")
    print(f"   Port: {port}")
    print(f"   LightRAG: {lightrag_url}")
    print(f"   API Key: {'Configured' if os.getenv('RAG_API_KEY') else 'Not Set'}")
    
    print("\n📡 Service will be available at:")
    print(f"   Local: http://localhost:{port}")
    if host == "0.0.0.0":
        print(f"   Network: http://YOUR_IP:{port}")
    print(f"   Docs: http://localhost:{port}/docs")
    
    print("\n" + "=" * 50)
    print("🚀 Starting API server...")
    
    try:
        # Start the API service
        subprocess.run([
            sys.executable, "rag_api_service.py"
        ], check=True)
    except KeyboardInterrupt:
        print("\n🛑 Service stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Service failed to start: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()