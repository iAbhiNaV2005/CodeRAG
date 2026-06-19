"""
CLI entry point for the Code RAG pipeline.

Usage:
    python -m src.main ingest <github_url>         # Ingest a repo
    python -m src.main query <repo_id> "<question>" # Ask a question
    python -m src.main chat <repo_id>              # Interactive multi-turn chat
"""

import argparse
import logging
import sys
import time

from dotenv import load_dotenv

# Load .env before importing modules that read settings
load_dotenv()

from src.fetcher import fetch_repo  # noqa: E402
from src.chunker import chunk_files  # noqa: E402
from src.embedder import embed_texts  # noqa: E402
from src.storage import insert_chunks, get_chunk_count, get_language_breakdown  # noqa: E402
from src.retriever import query  # noqa: E402

# ── Logging setup ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("code-rag")


def cmd_ingest(args: argparse.Namespace) -> None:
    """Ingest a GitHub repository: fetch -> chunk -> embed -> store."""
    repo_url = args.repo_url
    print(f"\n{'='*60}")
    print(f"  Ingesting: {repo_url}")
    print(f"{'='*60}\n")

    t_start = time.time()

    # Step 1: Fetch files from GitHub
    print("[>] Step 1/4 -- Fetching files from GitHub...")
    fetch_result = fetch_repo(repo_url, upload_to_s3=True)
    print(f"   + Fetched {len(fetch_result.files)} files, skipped {fetch_result.skipped_count}")
    print(f"   + Repo ID: {fetch_result.repo_id}")
    print(f"   + Commit:  {fetch_result.commit_hash[:12]}")

    if not fetch_result.files:
        print("\n[!] No code files found in this repository.")
        return

    # Step 2: Chunk files
    print("\n[*] Step 2/4 -- Chunking code files...")
    chunks = chunk_files(fetch_result.files, fetch_result.repo_id)
    print(f"   + Produced {len(chunks)} chunks")

    if not chunks:
        print("\n[!] No chunks produced. Check file filters and chunk settings.")
        return

    # Step 3: Embed chunks
    print("\n[*] Step 3/4 -- Embedding chunks (this may take a moment)...")
    chunk_texts = [c.content for c in chunks]
    embeddings = embed_texts(chunk_texts)
    print(f"   + Generated {len(embeddings)} embeddings (384-dim each)")

    # Step 4: Store in pgvector
    print("\n[*] Step 4/4 -- Storing in PostgreSQL + pgvector...")
    inserted = insert_chunks(chunks, embeddings)
    print(f"   + Inserted {inserted} rows")

    # Summary
    t_elapsed = time.time() - t_start
    lang_breakdown = get_language_breakdown(fetch_result.repo_id)

    print(f"\n{'='*60}")
    print(f"  [OK] Ingestion complete in {t_elapsed:.1f}s")
    print(f"  Repo ID:    {fetch_result.repo_id}")
    print(f"  Chunks:     {get_chunk_count(fetch_result.repo_id)}")
    print(f"  Languages:  {lang_breakdown}")
    print(f"{'='*60}\n")


def cmd_query(args: argparse.Namespace) -> None:
    """Run a single question against an ingested repository."""
    repo_id = args.repo_id
    question = args.question

    print(f"\n[?] Querying repo: {repo_id}")
    print(f"    Question: {question}\n")

    answer = query(question, repo_id)

    # Print answer
    print("-" * 60)
    print(answer.text)
    print("-" * 60)

    # Print sources
    if answer.sources:
        print(f"\n--- Sources ({len(answer.sources)}) ---")
        for i, src in enumerate(answer.sources, 1):
            print(f"   {i}. {src.file_path}:{src.start_line}-{src.end_line} "
                  f"(similarity: {src.similarity:.3f})")
    print()


def cmd_chat(args: argparse.Namespace) -> None:
    """Interactive multi-turn chat with an ingested repository."""
    repo_id = args.repo_id

    chunk_count = get_chunk_count(repo_id)
    if chunk_count == 0:
        print(f"\n[!] No chunks found for repo_id: {repo_id}")
        print("    Run 'ingest' first.\n")
        return

    print(f"\n[CHAT] Repo: {repo_id} ({chunk_count} chunks)")
    print("   Type 'quit' or 'exit' to end the session.")
    print("   Type 'clear' to reset chat history.")
    print("-" * 60)

    chat_history: list[dict[str, str]] = []

    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nSession ended.")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit"):
            print("\nSession ended.")
            break
        if question.lower() == "clear":
            chat_history.clear()
            print("   + Chat history cleared.")
            continue

        # Query with chat history for multi-turn context
        answer = query(question, repo_id, chat_history=chat_history)

        # Print answer
        print(f"\nAssistant:\n")
        print(answer.text)

        # Print sources
        if answer.sources:
            print(f"\n--- Sources ({len(answer.sources)}) ---")
            for i, src in enumerate(answer.sources, 1):
                print(f"   {i}. {src.file_path}:{src.start_line}-{src.end_line} "
                      f"({src.similarity:.3f})")

        # Append to chat history for multi-turn
        chat_history.append({"role": "user", "content": question})
        chat_history.append({"role": "assistant", "content": answer.text})


def main():
    parser = argparse.ArgumentParser(
        description="Code RAG Pipeline -- Ask questions about any GitHub codebase",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ingest
    ingest_parser = subparsers.add_parser("ingest", help="Ingest a GitHub repository")
    ingest_parser.add_argument("repo_url", help="GitHub URL (e.g. https://github.com/owner/repo)")

    # query (single question)
    query_parser = subparsers.add_parser("query", help="Ask a single question")
    query_parser.add_argument("repo_id", help="Repository ID from ingestion")
    query_parser.add_argument("question", help="Your question about the codebase")

    # chat (multi-turn)
    chat_parser = subparsers.add_parser("chat", help="Interactive multi-turn chat")
    chat_parser.add_argument("repo_id", help="Repository ID from ingestion")

    args = parser.parse_args()

    if args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "query":
        cmd_query(args)
    elif args.command == "chat":
        cmd_chat(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
