"""
Pydantic request/response models for the API.
"""

from pydantic import BaseModel, Field


# ── Ingest ───────────────────────────────────────────────────────
class IngestRequest(BaseModel):
    """Request body for POST /ingest."""
    repo_url: str = Field(
        ...,
        description="GitHub repository URL",
        examples=["https://github.com/expressjs/express"],
    )


class IngestResponse(BaseModel):
    """Response body for POST /ingest."""
    repo_id: str
    status: str  # PROCESSING, READY, FAILED
    message: str = ""


class IngestStatusResponse(BaseModel):
    """Response body for GET /ingest/status/{repo_id}."""
    repo_id: str
    status: str
    repo_url: str = ""
    commit_hash: str = ""
    chunk_count: int = 0
    language_breakdown: dict[str, int] = {}
    error_message: str | None = None


# ── Chat ─────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    """Request body for POST /chat."""
    session_id: str | None = Field(
        default=None,
        description="Session UUID. Omit to create a new session.",
    )
    repo_id: str = Field(
        ...,
        description="Repository ID to query against.",
    )
    question: str = Field(
        ...,
        description="The user's question about the codebase.",
        min_length=1,
        max_length=2000,
    )
    user_id: str = Field(
        default="anonymous",
        description="User identifier (from JWT in Phase 3).",
    )


# ── Health ───────────────────────────────────────────────────────
class HealthResponse(BaseModel):
    """Response body for GET /health."""
    status: str = "ok"
    service: str = "code-rag-pipeline"
    version: str = "0.1.0"
