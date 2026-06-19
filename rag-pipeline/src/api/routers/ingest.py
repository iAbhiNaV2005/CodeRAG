"""
Ingest router — handles repository ingestion with background processing.

POST /ingest         -> Start ingestion (returns immediately)
GET  /ingest/status/{repo_id} -> Check ingestion status
"""

import logging
import traceback

from fastapi import APIRouter, BackgroundTasks, HTTPException

from src.api.models import IngestRequest, IngestResponse, IngestStatusResponse
from src.fetcher import fetch_repo, parse_github_url, generate_repo_id
from src.chunker import chunk_files
from src.embedder import embed_texts
from src.storage import insert_chunks, get_chunk_count, get_language_breakdown, delete_repo_chunks
from src.dynamo.repos import get_repo, create_repo, update_repo_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["Ingestion"])


def _run_ingestion_pipeline(repo_id: str, repo_url: str) -> None:
    """
    Background task: runs the full ingestion pipeline.

    Fetch -> Chunk -> Embed -> Store -> Update DynamoDB status.
    This runs in a separate thread so /ingest returns immediately.
    """
    try:
        logger.info("Background ingestion started: %s (%s)", repo_id, repo_url)

        # Step 1: Fetch
        fetch_result = fetch_repo(repo_url, upload_to_s3=True)
        if not fetch_result.files:
            update_repo_status(repo_id, "FAILED", error_message="No code files found in repository")
            return

        # Step 2: Chunk
        chunks = chunk_files(fetch_result.files, fetch_result.repo_id)
        if not chunks:
            update_repo_status(repo_id, "FAILED", error_message="No chunks produced from code files")
            return

        # Step 3: Embed
        chunk_texts = [c.content for c in chunks]
        embeddings = embed_texts(chunk_texts)

        # Step 4: Store in pgvector
        # Delete any existing chunks for this repo (in case of re-ingestion)
        delete_repo_chunks(repo_id)
        inserted = insert_chunks(chunks, embeddings)

        # Step 5: Update DynamoDB with success
        chunk_count = get_chunk_count(repo_id)
        lang_breakdown = get_language_breakdown(repo_id)

        update_repo_status(
            repo_id,
            status="READY",
            chunk_count=chunk_count,
            language_breakdown=lang_breakdown,
        )

        logger.info(
            "Background ingestion complete: %s (%d chunks, languages: %s)",
            repo_id, chunk_count, lang_breakdown,
        )

    except Exception as e:
        logger.error("Ingestion failed for %s: %s\n%s", repo_id, e, traceback.format_exc())
        update_repo_status(
            repo_id,
            status="FAILED",
            error_message=str(e)[:500],
        )


@router.post("", response_model=IngestResponse)
async def ingest_repo(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start ingesting a GitHub repository.

    - If the repo was already ingested (READY), returns immediately with the cached result.
    - If currently processing, returns the current status.
    - Otherwise, starts background ingestion and returns immediately.
    """
    repo_url = request.repo_url.strip()

    # Parse and validate the URL
    try:
        owner, repo_name = parse_github_url(repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # We need the commit hash to generate repo_id, but for the fast path
    # we'll generate a preliminary ID to check DynamoDB cache.
    # For a full implementation, we'd fetch the latest commit first.
    # For now, check if any matching repo exists.

    # Try to get existing repo by checking DynamoDB
    # Generate a preliminary repo_id (we'll refine this when we actually fetch)
    from github import Github
    from src.config import get_settings
    settings = get_settings()

    try:
        gh = Github(settings.github_token) if settings.github_token else Github()
        repo = gh.get_repo(f"{owner}/{repo_name}")
        commit_hash = repo.get_branch(repo.default_branch).commit.sha
        repo_id = generate_repo_id(owner, repo_name, commit_hash)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not access repository: {e}",
        )

    # Check DynamoDB cache
    existing = get_repo(repo_id)

    if existing:
        status = existing.get("status", "UNKNOWN")

        if status == "READY":
            logger.info("Cache hit: %s is already ingested", repo_id)
            return IngestResponse(
                repo_id=repo_id,
                status="READY",
                message="Repository already ingested. Ready for queries.",
            )

        if status == "PROCESSING":
            logger.info("Repo %s is currently being processed", repo_id)
            return IngestResponse(
                repo_id=repo_id,
                status="PROCESSING",
                message="Repository is currently being ingested. Poll /ingest/status for updates.",
            )

        if status == "FAILED":
            # Re-try failed ingestion
            logger.info("Re-trying failed ingestion for %s", repo_id)

    # Create DynamoDB record and start background ingestion
    create_repo(repo_id, repo_url, commit_hash)
    background_tasks.add_task(_run_ingestion_pipeline, repo_id, repo_url)

    return IngestResponse(
        repo_id=repo_id,
        status="PROCESSING",
        message="Ingestion started. Poll /ingest/status for updates.",
    )


@router.get("/status/{repo_id}", response_model=IngestStatusResponse)
async def get_ingest_status(repo_id: str):
    """
    Check the status of a repository ingestion.

    Poll this endpoint until status is READY or FAILED.
    """
    repo = get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository {repo_id} not found")

    return IngestStatusResponse(
        repo_id=repo_id,
        status=repo.get("status", "UNKNOWN"),
        repo_url=repo.get("repo_url", ""),
        commit_hash=repo.get("commit_hash", ""),
        chunk_count=repo.get("chunk_count", 0),
        language_breakdown=repo.get("language_breakdown", {}),
        error_message=repo.get("error_message"),
    )
