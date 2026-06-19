"""
Centralized configuration via Pydantic BaseSettings.
Reads from .env file and environment variables.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # --- PostgreSQL ---
    postgres_url: str = Field(
        default="postgresql://coderag:coderag_dev@localhost:5432/coderag",
        description="PostgreSQL connection URL (must have pgvector extension)",
    )

    # --- AWS General ---
    aws_region: str = Field(default="us-east-1")
    aws_access_key_id: str = Field(default="test")
    aws_secret_access_key: str = Field(default="test")
    aws_endpoint_url: str | None = Field(
        default="http://localhost:4566",
        description="LocalStack endpoint for local dev. Set to None for real AWS.",
    )

    # --- S3 ---
    s3_bucket: str = Field(default="code-rag-repos")

    # --- DynamoDB table names ---
    dynamodb_repos_table: str = Field(default="repos")
    dynamodb_sessions_table: str = Field(default="sessions")
    dynamodb_rate_limits_table: str = Field(default="rate_limits")

    # --- GitHub ---
    github_token: str | None = Field(
        default=None,
        description="GitHub Personal Access Token for private repo access",
    )

    # --- Google AI (Gemini) ---
    google_api_key: str = Field(
        default="",
        description="Google AI API key for Gemini 1.5 Flash",
    )

    # --- Embedding ---
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="HuggingFace model name for code embeddings",
    )
    embedding_dimension: int = Field(default=384)
    embedding_batch_size: int = Field(default=64)

    # --- Chunking ---
    chunk_size: int = Field(default=1000, description="Characters per chunk")
    chunk_overlap: int = Field(default=200, description="Overlap between chunks")

    # --- Retrieval ---
    retrieval_top_k: int = Field(
        default=5, description="Number of chunks to retrieve per query"
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton — call this everywhere instead of instantiating Settings directly."""
    return Settings()
