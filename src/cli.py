"""Unified CLI for HermesContext RAG engine.

Provides local command-line access to all RAG operations without
external service dependencies. Mirrors all MCP tools.

Supports:
  - Semantic search
  - Document ingestion (direct text or from files)
  - Document listing, retrieval, deletion
  - Knowledge base statistics

Usage:
  hermes-cli search "query" [-k 5] [--no-rerank] [--json]
  hermes-cli ingest -t "Title" -c "content" [--json]
  hermes-cli ingest -t "Title" --stdin [--json]
  hermes-cli ingest-file <path> [--json]
  hermes-cli list [--limit 20] [--offset 0] [--json]
  hermes-cli get <doc-id> [--json]
  hermes-cli delete <doc-id> [--yes]
  hermes-cli stats [--json]
"""

import argparse
import json
import sys
from contextlib import contextmanager
from typing import Any, Optional


def _has_color_support() -> bool:
    """Check if terminal supports color (disable in pipes)."""
    return sys.stdout.isatty()


@contextmanager
def hermes_session():
    """Context manager for RAG engine initialization with lazy imports.

    Delays imports until needed so --help is instantaneous.
    """
    from .database import Database
    from .embeddings import EmbeddingService
    from .engine import RAGEngine

    db = Database()
    db.connect()
    db.init_schema()

    emb = EmbeddingService()
    engine = RAGEngine(db=db, emb=emb)

    try:
        yield engine, db
    finally:
        db.close()


def _format_with_color(text: str, color: str) -> str:
    """Apply ANSI color if terminal supports it."""
    if not _has_color_support():
        return text

    colors = {
        "bold": "\033[1m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "cyan": "\033[96m",
        "reset": "\033[0m",
    }
    return f"{colors.get(color, '')}{text}{colors.get('reset', '')}"


def cmd_search(args: argparse.Namespace) -> int:
    """Execute semantic search command."""
    query = args.query
    top_k = args.k
    use_reranker = not args.no_rerank
    as_json = args.json

    with hermes_session() as (engine, _):
        results = engine.search(
            query=query,
            top_k=top_k,
            use_reranker=use_reranker,
        )

        if as_json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            print(f"Query: {_format_with_color(query, 'cyan')}")
            print(f"Results: {len(results['results'])} / {results['total_candidates']} ({results['elapsed_ms']}ms)\n")

            for i, r in enumerate(results["results"], 1):
                score = r.get("rerank_score") or r.get("rrf_score") or r.get("score", 0)
                title = r.get("document_title", "No title")
                print(f"{i}. {_format_with_color(title, 'bold')} (score: {score:.3f})")
                print(f"   Doc: {r['document_id']} | Chunk: {r['chunk_id']}")
                print(f"   {r['chunk_text'][:200]}...")
                print()

    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    """Execute document ingestion command."""
    title = args.title
    content = args.content
    use_stdin = args.stdin
    as_json = args.json

    if use_stdin:
        if content:
            print(_format_with_color("Error: cannot use both -c and --stdin", "red"), file=sys.stderr)
            return 1
        content = sys.stdin.read()

    if not content:
        print(_format_with_color("Error: no content provided", "red"), file=sys.stderr)
        return 1

    with hermes_session() as (engine, _):
        result = engine.ingest_document(
            title=title,
            content=content,
            source=None,
            doc_type=None,
            metadata=None,
        )

        if as_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"✅ Document ingested")
            print(f"   ID: {result['document_id']}")
            print(f"   Title: {result['title']}")
            print(f"   Chunks: {result['chunk_count']}")
            print(f"   Time: {result['elapsed_ms']}ms")

    return 0


def cmd_ingest_file(args: argparse.Namespace) -> int:
    """Execute file ingestion command."""
    from .utils import read_file_from_disk
    import os

    path = args.path
    as_json = args.json

    if not os.path.exists(path):
        print(_format_with_color(f"Error: path not found: {path}", "red"), file=sys.stderr)
        return 1

    try:
        content = read_file_from_disk(path)
    except ValueError as e:
        print(_format_with_color(f"Error: {e}", "red"), file=sys.stderr)
        return 1

    if not content.strip():
        print(_format_with_color("Error: file is empty", "red"), file=sys.stderr)
        return 1

    title = os.path.splitext(os.path.basename(path))[0]

    with hermes_session() as (engine, _):
        result = engine.ingest_document(
            title=title,
            content=content,
            source=path,
            doc_type=None,
            metadata={"filename": os.path.basename(path), "size_chars": len(content)},
        )

        if as_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"✅ File ingested")
            print(f"   Path: {path}")
            print(f"   ID: {result['document_id']}")
            print(f"   Chunks: {result['chunk_count']}")
            print(f"   Time: {result['elapsed_ms']}ms")

    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """Execute document listing command."""
    limit = args.limit
    offset = args.offset
    as_json = args.json

    with hermes_session() as (_, db):
        data = db.list_documents(limit=limit, offset=offset, doc_type=None)

        if as_json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(f"Documents ({data['total']} total)\n")
            for doc in data["items"]:
                print(f"[{doc['id']}] {_format_with_color(doc['title'], 'bold')}")
                print(f"    Type: {doc['doc_type'] or '—'} | Chunks: {doc['chunk_count']} | Created: {doc['created_at']}")

            if data["has_more"]:
                next_off = offset + limit
                print(f"\nMore results available (--offset {next_off})")

    return 0


def cmd_get(args: argparse.Namespace) -> int:
    """Execute document retrieval command."""
    doc_id = args.doc_id
    as_json = args.json

    with hermes_session() as (_, db):
        doc = db.get_document(doc_id)

        if not doc:
            print(_format_with_color(f"Error: document {doc_id} not found", "red"), file=sys.stderr)
            return 1

        if as_json:
            print(json.dumps(doc, indent=2, ensure_ascii=False))
        else:
            print(f"Document #{doc['id']}: {_format_with_color(doc['title'], 'bold')}")
            print(f"  Source: {doc['source'] or '—'}")
            print(f"  Type: {doc['doc_type'] or '—'}")
            print(f"  Chunks: {doc['chunk_count']}")
            print(f"  Created: {doc['created_at']}")
            if doc.get("metadata"):
                print("  Metadata:")
                for k, v in doc["metadata"].items():
                    print(f"    - {k}: {v}")

    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    """Execute document deletion command."""
    doc_id = args.doc_id
    skip_confirm = args.yes

    with hermes_session() as (_, db):
        doc = db.get_document(doc_id)

        if not doc:
            print(_format_with_color(f"Error: document {doc_id} not found", "red"), file=sys.stderr)
            return 1

        if not skip_confirm:
            msg = f"Delete document #{doc_id} '{doc['title']}'? [y/N] "
            try:
                response = input(_format_with_color(msg, "yellow")).strip().lower()
            except EOFError:
                response = "n"

            if response != "y":
                print("Cancelled.")
                return 0

        deleted = db.delete_document(doc_id)

        if deleted:
            print(f"✅ Document #{doc_id} deleted")
        else:
            print(_format_with_color(f"Error: could not delete document {doc_id}", "red"), file=sys.stderr)
            return 1

    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Execute statistics command."""
    as_json = args.json

    with hermes_session() as (_, db):
        stats = db.get_stats()

        if as_json:
            print(json.dumps(stats, indent=2, ensure_ascii=False))
        else:
            print("RAG Base Statistics")
            print(f"  Documents: {stats['documents']}")
            print(f"  Chunks: {stats['chunks']}")
            print(f"  Total tokens: {stats['total_tokens']:,}")
            if stats["by_type"]:
                print("  By type:")
                for t, c in stats["by_type"].items():
                    print(f"    - {t}: {c}")

    return 0


def main() -> None:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="hermes-cli",
        description="HermesContext RAG CLI — semantic search, document management",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    subparsers.required = True

    # search
    search_parser = subparsers.add_parser("search", help="Semantic search")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("-k", type=int, default=5, help="Number of results (default: 5)")
    search_parser.add_argument("--no-rerank", action="store_true", help="Disable reranking")
    search_parser.add_argument("--json", action="store_true", help="JSON output")
    search_parser.set_defaults(func=cmd_search)

    # ingest
    ingest_parser = subparsers.add_parser("ingest", help="Ingest document")
    ingest_parser.add_argument("-t", "--title", required=True, help="Document title")
    ingest_parser.add_argument("-c", "--content", help="Document content")
    ingest_parser.add_argument("--stdin", action="store_true", help="Read content from stdin")
    ingest_parser.add_argument("--json", action="store_true", help="JSON output")
    ingest_parser.set_defaults(func=cmd_ingest)

    # ingest-file
    ingest_file_parser = subparsers.add_parser("ingest-file", help="Ingest file (txt, md, pdf, etc)")
    ingest_file_parser.add_argument("path", help="Path to file")
    ingest_file_parser.add_argument("--json", action="store_true", help="JSON output")
    ingest_file_parser.set_defaults(func=cmd_ingest_file)

    # list
    list_parser = subparsers.add_parser("list", help="List documents")
    list_parser.add_argument("--limit", type=int, default=20, help="Maximum results (default: 20)")
    list_parser.add_argument("--offset", type=int, default=0, help="Pagination offset (default: 0)")
    list_parser.add_argument("--json", action="store_true", help="JSON output")
    list_parser.set_defaults(func=cmd_list)

    # get
    get_parser = subparsers.add_parser("get", help="Get document details")
    get_parser.add_argument("doc_id", type=int, help="Document ID")
    get_parser.add_argument("--json", action="store_true", help="JSON output")
    get_parser.set_defaults(func=cmd_get)

    # delete
    delete_parser = subparsers.add_parser("delete", help="Delete document")
    delete_parser.add_argument("doc_id", type=int, help="Document ID")
    delete_parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    delete_parser.set_defaults(func=cmd_delete)

    # stats
    stats_parser = subparsers.add_parser("stats", help="Show statistics")
    stats_parser.add_argument("--json", action="store_true", help="JSON output")
    stats_parser.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    exit_code = args.func(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
