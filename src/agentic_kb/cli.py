"""Command Line Interface (CLI) for agentic-kb."""

import argparse
import sys
import uvicorn
from agentic_kb.api.app import create_app


def main():
    parser = argparse.ArgumentParser(description="Agentic KnowledgeBase CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # 'serve' command
    serve_parser = subparsers.add_parser("serve", help="Start the FastAPI REST API server")
    serve_parser.add_argument("--config", "-c", default="configs/example.yaml", help="Path to YAML config file")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    serve_parser.add_argument("--port", "-p", type=int, default=8000, help="Bind port (default: 8000)")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    # 'check' command
    check_parser = subparsers.add_parser("check", help="Run health check and verify configuration")
    check_parser.add_argument("--config", "-c", default="configs/example.yaml", help="Path to YAML config file")

    args = parser.parse_args()

    if args.command == "serve":
        print(f"Starting Agentic KnowledgeBase server on http://{args.host}:{args.port} (config={args.config})")
        app = create_app(config_path=args.config)
        uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
    elif args.command == "check":
        from agentic_kb.agent.agent import AgenticKnowledgeBase
        agent = AgenticKnowledgeBase.from_yaml(args.config)
        health = agent.health_check()
        print("Health Check Result:")
        print(health)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
