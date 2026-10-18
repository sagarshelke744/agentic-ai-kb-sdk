"""Command Line Interface (CLI) for agentic-kb."""

import argparse
import sys
import uvicorn
from agentic_kb.api.app import create_app


def _catalog_generate(args) -> None:
    from pathlib import Path

    from agentic_kb.agent.agent import AgenticKnowledgeBase
    from agentic_kb.knowledgebase.catalog import CatalogBuilder, dump_catalog, load_catalog

    agent = AgenticKnowledgeBase.from_yaml(args.config)
    kb_cfg = agent.config.knowledgebase
    out = Path(args.output or kb_cfg.catalog_file or "catalog.yaml")

    print(f"Reading schema from '{agent.config.database.database}' ({len(kb_cfg.allowed_tables)} allowed tables) ...")
    schema = agent.db.get_schema_metadata(
        allowed_schemas=kb_cfg.allowed_schemas, allowed_tables=kb_cfg.allowed_tables
    )
    if not schema.tables:
        print("No tables found. Check knowledgebase.allowed_schemas / allowed_tables in your config.")
        sys.exit(1)

    existing = load_catalog(out)
    if existing and not args.overwrite:
        print(f"Existing {out} found - your edited descriptions and relations will be kept.")

    builder = CatalogBuilder(
        db=agent.db,
        schema=schema,
        llm=None if args.no_llm else agent.llm,
        exclude_columns=kb_cfg.catalog_exclude_columns,
        table_descriptions=kb_cfg.table_descriptions,
        log=print,
    )
    print("Profiling tables:")
    catalog = builder.build(
        existing=existing,
        profile_values=not args.no_samples,
        use_llm=not args.no_llm,
        overwrite=args.overwrite,
    )
    dump_catalog(catalog, out)
    agent.close()

    print(f"\nWrote {out}  ({len(catalog['tables'])} tables)")
    for w in builder.warnings:
        print(f"  ! {w}")
    if builder.review:
        print(f"\nPlease review these {len(builder.review)} auto-generated items "
              "(fix the text, then delete `needs_review`):")
        for item in builder.review:
            print(f"  - {item}")
    else:
        print("\nNothing marked for review.")
    print("\nNext steps:")
    print(f"  1. Open {out}, review and edit.")
    if kb_cfg.catalog_file != str(out):
        print(f"  2. Add to your config under `knowledgebase:`  ->  catalog_file: {out}")
    else:
        print("  2. Your config already points to this file.")
    print(f"  3. Preview what the LLM will see:  agentic-kb catalog show -c {args.config}")


def _catalog_show(args) -> None:
    from agentic_kb.agent.agent import AgenticKnowledgeBase

    agent = AgenticKnowledgeBase.from_yaml(args.config)
    if not agent.config.knowledgebase.catalog_file:
        print("Note: knowledgebase.catalog_file is not set in this config - showing reflected schema only.\n")
    print(agent.get_schema_metadata(use_cache=False).to_prompt_context())
    agent.close()


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

    # 'catalog' command group
    catalog_parser = subparsers.add_parser(
        "catalog", help="Generate and preview the schema catalog (descriptions, sample values, relations)"
    )
    catalog_sub = catalog_parser.add_subparsers(dest="catalog_command", help="Catalog action")

    gen = catalog_sub.add_parser("generate", help="Profile the database and write a reviewable catalog YAML")
    gen.add_argument("--config", "-c", default="configs/example.yaml", help="Path to YAML config file")
    gen.add_argument("--output", "-o", default=None, help="Output file (default: knowledgebase.catalog_file or catalog.yaml)")
    gen.add_argument("--no-llm", action="store_true", help="Don't call the LLM to write missing descriptions")
    gen.add_argument("--no-samples", action="store_true", help="Don't read data: no value profiling, no sample rows to the LLM")
    gen.add_argument("--overwrite", action="store_true", help="Discard existing descriptions/relations and regenerate everything")

    show = catalog_sub.add_parser("show", help="Print the schema context exactly as the LLM will see it")
    show.add_argument("--config", "-c", default="configs/example.yaml", help="Path to YAML config file")

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
    elif args.command == "catalog":
        if args.catalog_command == "generate":
            _catalog_generate(args)
        elif args.catalog_command == "show":
            _catalog_show(args)
        else:
            catalog_parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
