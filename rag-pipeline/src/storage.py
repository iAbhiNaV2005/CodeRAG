"""
pgvector storage layer.

Handles inserting code chunks with embeddings and running
cosine similarity searches against the code_chunks table.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.chunker import CodeChunk
from src.config import get_settings

logger = logging.getLogger(__name__)


# ── SQLAlchemy ORM model ─────────────────────────────────────────
class Base(DeclarativeBase):
    pass


class CodeChunkRow(Base):
    """ORM model for the code_chunks table."""

    __tablename__ = "code_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(String(255), nullable=False, index=True)
    file_path = Column(Text, nullable=False)
    language = Column(String(20), nullable=False)
    start_line = Column(Integer, nullable=False)
    end_line = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(384), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


# ── Engine & session factory (singleton) ─────────────────────────
_engine = None
_SessionFactory = None


def _get_session_factory() -> sessionmaker:
    """Get or create the SQLAlchemy session factory."""
    global _engine, _SessionFactory
    if _SessionFactory is None:
        settings = get_settings()
        _engine = create_engine(
            settings.postgres_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
        _SessionFactory = sessionmaker(bind=_engine)
        logger.info("Database engine created: %s", settings.postgres_url.split("@")[-1])
    return _SessionFactory


def get_db_session() -> Session:
    """Create a new database session."""
    factory = _get_session_factory()
    return factory()


# ── Search result dataclass ──────────────────────────────────────
@dataclass
class SearchResult:
    """A single search result from pgvector similarity search."""

    id: str
    repo_id: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    content: str
    similarity: float


# ── Public API ───────────────────────────────────────────────────
def insert_chunks(chunks: list[CodeChunk], embeddings: list[list[float]]) -> int:
    """
    Bulk insert code chunks with their embeddings into PostgreSQL.

    Args:
        chunks: List of CodeChunk objects from the chunker.
        embeddings: Corresponding list of embedding vectors.

    Returns:
        Number of rows inserted.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"Mismatch: {len(chunks)} chunks but {len(embeddings)} embeddings"
        )

    session = get_db_session()
    try:
        rows = []
        for chunk, embedding in zip(chunks, embeddings):
            row = CodeChunkRow(
                repo_id=chunk.repo_id,
                file_path=chunk.file_path,
                language=chunk.language,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                content=chunk.content,
                embedding=embedding,
            )
            rows.append(row)

        # Batch insert
        session.add_all(rows)
        session.commit()

        logger.info("Inserted %d chunks for repo %s", len(rows), chunks[0].repo_id if chunks else "?")
        return len(rows)

    except Exception as e:
        session.rollback()
        logger.error("Failed to insert chunks: %s", e)
        raise
    finally:
        session.close()


def search_similar(
    query_embedding: list[float],
    repo_id: str,
    top_k: int | None = None,
) -> list[SearchResult]:
    """
    Find the most similar code chunks to a query embedding using pgvector.

    Uses cosine distance operator (<=>). Filters by repo_id so different
    repos don't pollute each other's results.

    Args:
        query_embedding: The embedded user question (384-dim vector).
        repo_id: Only search chunks belonging to this repository.
        top_k: Number of results to return (defaults to settings.retrieval_top_k).

    Returns:
        List of SearchResult objects ordered by similarity (most similar first).
    """
    settings = get_settings()
    if top_k is None:
        top_k = settings.retrieval_top_k

    session = get_db_session()
    try:
        # Use raw SQL for the pgvector cosine distance operator
        # 1 - cosine_distance gives us cosine similarity (0 to 1, higher is better)
        query = text("""
            SELECT
                id,
                repo_id,
                file_path,
                language,
                start_line,
                end_line,
                content,
                1 - (embedding <=> :query_embedding) AS similarity
            FROM code_chunks
            WHERE repo_id = :repo_id
            ORDER BY embedding <=> :query_embedding
            LIMIT :top_k
        """)

        result = session.execute(
            query,
            {
                "query_embedding": str(query_embedding),
                "repo_id": repo_id,
                "top_k": top_k,
            },
        )

        search_results = []
        for row in result:
            search_results.append(
                SearchResult(
                    id=str(row.id),
                    repo_id=row.repo_id,
                    file_path=row.file_path,
                    language=row.language,
                    start_line=row.start_line,
                    end_line=row.end_line,
                    content=row.content,
                    similarity=float(row.similarity),
                )
            )

        logger.info(
            "Search returned %d results (repo: %s, top similarity: %.4f)",
            len(search_results),
            repo_id,
            search_results[0].similarity if search_results else 0.0,
        )

        return search_results

    except Exception as e:
        logger.error("Similarity search failed: %s", e)
        raise
    finally:
        session.close()


def delete_repo_chunks(repo_id: str) -> int:
    """
    Delete all chunks for a given repo_id.
    Useful for re-ingestion.

    Returns:
        Number of rows deleted.
    """
    session = get_db_session()
    try:
        result = session.execute(
            text("DELETE FROM code_chunks WHERE repo_id = :repo_id"),
            {"repo_id": repo_id},
        )
        session.commit()
        deleted = result.rowcount
        logger.info("Deleted %d chunks for repo %s", deleted, repo_id)
        return deleted
    except Exception as e:
        session.rollback()
        logger.error("Failed to delete chunks: %s", e)
        raise
    finally:
        session.close()


def get_chunk_count(repo_id: str) -> int:
    """Get the total number of chunks stored for a repo."""
    session = get_db_session()
    try:
        result = session.execute(
            text("SELECT COUNT(*) FROM code_chunks WHERE repo_id = :repo_id"),
            {"repo_id": repo_id},
        )
        return result.scalar() or 0
    finally:
        session.close()


def get_language_breakdown(repo_id: str) -> dict[str, int]:
    """Get the count of chunks per language for a repo."""
    session = get_db_session()
    try:
        result = session.execute(
            text("""
                SELECT language, COUNT(*) as cnt
                FROM code_chunks
                WHERE repo_id = :repo_id
                GROUP BY language
                ORDER BY cnt DESC
            """),
            {"repo_id": repo_id},
        )
        return {row.language: row.cnt for row in result}
    finally:
        session.close()
