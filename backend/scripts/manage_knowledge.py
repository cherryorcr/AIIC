"""题库/来源 SQLite 管理命令。

Examples (run from ``backend``):
    python scripts/manage_knowledge.py init
    python scripts/manage_knowledge.py stats
    python scripts/manage_knowledge.py list --process-type 算法面
    python scripts/manage_knowledge.py reload --prune

The command intentionally uses the same Database and GraphRAG code as the API,
so local imports and production imports have identical idempotency semantics.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow ``python scripts/manage_knowledge.py`` when launched from the backend
# directory (Python otherwise only adds the scripts directory to sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.services.rag import GraphRAGService
from app.storage.db import Database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage interview knowledge data")
    parser.add_argument("command", choices=("init", "stats", "list", "sources", "reload"))
    parser.add_argument("--process-type", default=None, help="Filter by interview stage, e.g. 算法面")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--prune", action="store_true", help="Soft-delete questions removed from the dataset")
    parser.add_argument("--include-inactive", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    db = Database(Path(settings.database_path), database_url=settings.database_url)
    try:
        db.init()
        if args.command == "init":
            print(json.dumps({"status": "initialized", "database": str(db.path)}, ensure_ascii=False))
        elif args.command == "stats":
            print(json.dumps(db.knowledge_stats(), ensure_ascii=False, indent=2))
        elif args.command == "list":
            print(json.dumps(
                db.list_questions(
                    process_type=args.process_type,
                    limit=args.limit,
                    include_inactive=args.include_inactive,
                ),
                ensure_ascii=False,
                indent=2,
            ))
        elif args.command == "sources":
            print(json.dumps(db.list_sources(args.limit), ensure_ascii=False, indent=2))
        elif args.command == "reload":
            rag = GraphRAGService(Path(settings.dataset_path))
            processed = db.seed_questions(rag.items, prune=args.prune)
            print(json.dumps({**db.knowledge_stats(), "items_processed": processed, "prune": args.prune}, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
