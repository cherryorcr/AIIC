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
import hashlib
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
    parser.add_argument("command", choices=("init", "stats", "list", "sources", "reload", "import", "validate"))
    parser.add_argument("--process-type", default=None, help="Filter by interview stage, e.g. 算法面")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--prune", action="store_true", help="Soft-delete questions removed from the dataset")
    parser.add_argument("--include-inactive", action="store_true")
    parser.add_argument("--file", help="JSON file containing {items: [...]} or an item array")
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
        elif args.command in {"import", "validate"}:
            if not args.file:
                raise SystemExit(f"{args.command} requires --file")
            source_path = Path(args.file)
            payload = json.loads(source_path.read_text(encoding="utf-8"))
            items = payload.get("items", payload) if isinstance(payload, dict) else payload
            if not isinstance(items, list):
                raise SystemExit("input must be a JSON array or an object with an items array")
            normalized = []
            seen = set()
            errors = []
            for index, item in enumerate(items):
                if not isinstance(item, dict) or not str(item.get("question", "")).strip():
                    errors.append({"index": index, "error": "question_required"})
                    continue
                question = " ".join(str(item["question"]).split())
                fingerprint = hashlib.sha256(question.lower().encode("utf-8")).hexdigest()
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                current = dict(item)
                source = dict(current.get("source") or {})
                source_type = source.get("type") or source.get("source_type") or "online"
                if source_type not in {"synthetic_mock", "synthetic", "online", "official", "user_submitted"}:
                    errors.append({"index": index, "error": "source_type_invalid"})
                    continue
                if source_type in {"online", "official"} and not source.get("url"):
                    errors.append({"index": index, "error": "source_url_required"})
                    continue
                source["content_hash"] = source.get("content_hash") or fingerprint
                source["accessed_at"] = source.get("accessed_at") or source.get("collected_at")
                current["question"] = question
                current["source"] = source
                normalized.append(current)
            if args.command == "validate":
                print(json.dumps({"valid": not errors, "accepted": len(normalized), "errors": errors}, ensure_ascii=False, indent=2))
            else:
                processed = db.seed_questions(normalized, prune=args.prune)
                print(json.dumps({**db.knowledge_stats(), "items_processed": processed, "accepted": len(normalized), "errors": errors}, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
