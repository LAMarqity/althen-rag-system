#!/usr/bin/env python3
import sys
import os
from pathlib import Path

def main():
    print("Starting Althen RAG System...")
    print("=" * 50)
    
    # Grundläggande kontroller
    current_dir = Path.cwd()
    print(f"Current directory: {current_dir}")
    
    # Kontrollera .env
    env_file = current_dir / ".env"
    print(f".env file exists: {env_file.exists()}")
    
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
            print(f"Loaded environment from: {env_file}")
        except ImportError:
            print("python-dotenv not installed. Run: pip install python-dotenv")
            return 1
        except Exception as e:
            print(f"Error loading .env: {e}")
            return 1
    else:
        print("No .env file found. Please create one with your API keys.")
        return 1
    
    # Kontrollera Supabase-variabler (OpenAI är valfritt för test)
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_ANON_KEY")
    
    if not supabase_url or not supabase_key:
        print("Missing SUPABASE_URL or SUPABASE_ANON_KEY")
        return 1
    
    print("All environment variables found")
    print("Supabase URL:", supabase_url)
    print("Working directory:", os.getenv("WORKING_DIR", "./knowledge_base"))
    
    # Kontrollera scripts directory
    scripts_dir = current_dir / "scripts"
    print(f"Scripts directory exists: {scripts_dir.exists()}")
    
    if not scripts_dir.exists():
        print("Scripts directory not found. Please create it.")
        return 1
    
    # Lägg till scripts till Python path
    sys.path.insert(0, str(scripts_dir))
    
    # Testa import av huvudmodul
    try:
        print("Importing althen_rag_service...")
        from althen_rag_service import main as rag_main
        print("Import successful")
    except ImportError as e:
        print(f"Import error: {e}")
        print("Please check that scripts/althen_rag_service.py exists")
        return 1
    except Exception as e:
        print(f"Error importing: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Testa async import
    try:
        import asyncio
        print("asyncio import OK")
    except ImportError as e:
        print(f"asyncio import failed: {e}")
        return 1
    
    print("=" * 50)
    
    # Kör huvudprogrammet
    try:
        exit_code = asyncio.run(rag_main())
        return exit_code
    except Exception as e:
        print(f"Error running main program: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)