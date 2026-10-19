"""
Start the Agentic KB API Server with SQL Server (DESKTOP-EF69CVF\\SQLEXPRESS / Sagar)
Run from project root:
    python examples/start_sqlserver_api.py
"""
import os
from dotenv import load_dotenv
load_dotenv()

import uvicorn
from agentic_kb.api.app import create_app

if __name__ == "__main__":
    provider = "openai" if os.getenv("OPENAI_API_KEY") else ("groq" if os.getenv("GROQ_API_KEY") else "missing")
    print(f"Starting Agentic KB API -> SQL Server (DESKTOP-EF69CVF\\SQLEXPRESS / Sagar)")
    print(f"API docs : http://localhost:8000/docs")
    print(f"Chat API : http://localhost:8000/api/v1/chat")
    print(f"Frontend : http://localhost:3000")
    print(f"LLM Key  : {'Detected (' + provider + ')' if provider != 'missing' else 'NOT DETECTED in .env'}\n")

    app = create_app(config_path="configs/sqlserver.yaml")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False,
    )
