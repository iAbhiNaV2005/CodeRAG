"""
DynamoDB CRUD operations for the repos table.

Tracks repository ingestion state: PENDING -> PROCESSING -> READY | FAILED.
Uses TTL for auto-cleanup of stale repos (7 days).
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import ClientError

from src.config import get_settings
from src.dynamo.client import get_table

logger = logging.getLogger(__name__)

# TTL: 7 days in seconds
REPO_TTL_SECONDS = 7 * 24 * 60 * 60


def _get_repos_table():
    settings = get_settings()
    return get_table(settings.dynamodb_repos_table)


def get_repo(repo_id: str) -> dict[str, Any] | None:
    """
    Get a repo record by repo_id.

    Returns:
        The repo dict, or None if not found.
    """
    table = _get_repos_table()
    try:
        response = table.get_item(Key={"repo_id": repo_id})
        item = response.get("Item")
        if item:
            logger.debug("Found repo: %s (status: %s)", repo_id, item.get("status"))
        return item
    except ClientError as e:
        logger.error("Failed to get repo %s: %s", repo_id, e)
        return None


def create_repo(
    repo_id: str,
    repo_url: str,
    commit_hash: str,
) -> dict[str, Any]:
    """
    Create a new repo record with status=PROCESSING.

    Returns:
        The created repo dict.
    """
    table = _get_repos_table()
    now = datetime.now(timezone.utc).isoformat()
    ttl = int(time.time()) + REPO_TTL_SECONDS

    item = {
        "repo_id": repo_id,
        "repo_url": repo_url,
        "commit_hash": commit_hash,
        "status": "PROCESSING",
        "chunk_count": 0,
        "language_breakdown": {},
        "ingested_at": now,
        "updated_at": now,
        "error_message": None,
        "ttl": ttl,
    }

    table.put_item(Item=item)
    logger.info("Created repo record: %s (status: PROCESSING)", repo_id)
    return item


def update_repo_status(
    repo_id: str,
    status: str,
    chunk_count: int | None = None,
    language_breakdown: dict[str, int] | None = None,
    error_message: str | None = None,
) -> None:
    """
    Update a repo's status and optional metadata.

    Args:
        repo_id: The repository identifier.
        status: New status (PROCESSING, READY, FAILED).
        chunk_count: Total number of chunks stored.
        language_breakdown: Mapping of language -> chunk count.
        error_message: Error message if status is FAILED.
    """
    table = _get_repos_table()
    now = datetime.now(timezone.utc).isoformat()

    update_expr_parts = ["#status = :status", "updated_at = :updated_at"]
    expr_names = {"#status": "status"}
    expr_values: dict[str, Any] = {
        ":status": status,
        ":updated_at": now,
    }

    if chunk_count is not None:
        update_expr_parts.append("chunk_count = :chunk_count")
        expr_values[":chunk_count"] = chunk_count

    if language_breakdown is not None:
        update_expr_parts.append("language_breakdown = :lang")
        expr_values[":lang"] = language_breakdown

    if error_message is not None:
        update_expr_parts.append("error_message = :error")
        expr_values[":error"] = error_message

    table.update_item(
        Key={"repo_id": repo_id},
        UpdateExpression="SET " + ", ".join(update_expr_parts),
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )

    logger.info("Updated repo %s -> status=%s", repo_id, status)


def delete_repo(repo_id: str) -> None:
    """Delete a repo record."""
    table = _get_repos_table()
    table.delete_item(Key={"repo_id": repo_id})
    logger.info("Deleted repo record: %s", repo_id)
