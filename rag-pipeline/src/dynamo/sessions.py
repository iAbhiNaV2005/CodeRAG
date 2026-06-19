"""
DynamoDB CRUD operations for the sessions table.

Maps session_id -> repo_id, tracks message count and chat history.
Uses TTL for auto-cleanup (24 hours).
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import ClientError

from src.config import get_settings
from src.dynamo.client import get_table

logger = logging.getLogger(__name__)

# TTL: 24 hours in seconds
SESSION_TTL_SECONDS = 24 * 60 * 60

# Maximum number of chat history entries to store per session
MAX_CHAT_HISTORY = 20


def _get_sessions_table():
    settings = get_settings()
    return get_table(settings.dynamodb_sessions_table)


def get_session(session_id: str) -> dict[str, Any] | None:
    """
    Get a session record by session_id.

    Returns:
        The session dict, or None if not found.
    """
    table = _get_sessions_table()
    try:
        response = table.get_item(Key={"session_id": session_id})
        return response.get("Item")
    except ClientError as e:
        logger.error("Failed to get session %s: %s", session_id, e)
        return None


def get_or_create_session(
    session_id: str | None,
    repo_id: str,
    user_id: str = "anonymous",
) -> dict[str, Any]:
    """
    Get an existing session or create a new one.

    If session_id is None, generates a new UUID.

    Args:
        session_id: Existing session UUID, or None to create new.
        repo_id: Repository this session is chatting about.
        user_id: User identifier (from JWT or anonymous).

    Returns:
        The session dict (existing or newly created).
    """
    # If session_id provided, try to fetch existing session
    if session_id:
        existing = get_session(session_id)
        if existing:
            # Refresh TTL on access
            _refresh_ttl(session_id)
            return existing

    # Create new session
    if not session_id:
        session_id = str(uuid.uuid4())

    table = _get_sessions_table()
    now = datetime.now(timezone.utc).isoformat()
    ttl = int(time.time()) + SESSION_TTL_SECONDS

    item = {
        "session_id": session_id,
        "repo_id": repo_id,
        "user_id": user_id,
        "message_count": 0,
        "chat_history": [],  # List of {"role": "user"|"assistant", "content": "..."}
        "created_at": now,
        "last_active": now,
        "ttl": ttl,
    }

    table.put_item(Item=item)
    logger.info("Created session: %s (repo: %s, user: %s)", session_id, repo_id, user_id)
    return item


def _refresh_ttl(session_id: str) -> None:
    """Refresh the session TTL and last_active timestamp."""
    table = _get_sessions_table()
    now = datetime.now(timezone.utc).isoformat()
    ttl = int(time.time()) + SESSION_TTL_SECONDS

    try:
        table.update_item(
            Key={"session_id": session_id},
            UpdateExpression="SET last_active = :now, #ttl = :ttl",
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={":now": now, ":ttl": ttl},
        )
    except ClientError as e:
        logger.warning("Failed to refresh TTL for session %s: %s", session_id, e)


def append_chat_message(
    session_id: str,
    role: str,
    content: str,
) -> None:
    """
    Append a message to the session's chat history and increment message count.

    Keeps only the last MAX_CHAT_HISTORY entries to prevent unbounded growth.

    Args:
        session_id: The session UUID.
        role: "user" or "assistant".
        content: The message text.
    """
    session = get_session(session_id)
    if not session:
        logger.warning("Session %s not found, cannot append message", session_id)
        return

    # Get existing history, append new message
    history = session.get("chat_history", [])
    history.append({"role": role, "content": content})

    # Trim to last MAX_CHAT_HISTORY entries
    if len(history) > MAX_CHAT_HISTORY:
        history = history[-MAX_CHAT_HISTORY:]

    table = _get_sessions_table()
    now = datetime.now(timezone.utc).isoformat()
    ttl = int(time.time()) + SESSION_TTL_SECONDS

    table.update_item(
        Key={"session_id": session_id},
        UpdateExpression=(
            "SET chat_history = :history, "
            "message_count = message_count + :inc, "
            "last_active = :now, "
            "#ttl = :ttl"
        ),
        ExpressionAttributeNames={"#ttl": "ttl"},
        ExpressionAttributeValues={
            ":history": history,
            ":inc": 1,
            ":now": now,
            ":ttl": ttl,
        },
    )

    logger.debug("Appended %s message to session %s (total: %d)", role, session_id, len(history))


def get_chat_history(session_id: str) -> list[dict[str, str]]:
    """
    Get the chat history for a session.

    Returns:
        List of message dicts: [{"role": "user"|"assistant", "content": "..."}]
    """
    session = get_session(session_id)
    if not session:
        return []
    return session.get("chat_history", [])


def delete_session(session_id: str) -> None:
    """Delete a session record."""
    table = _get_sessions_table()
    table.delete_item(Key={"session_id": session_id})
    logger.info("Deleted session: %s", session_id)
