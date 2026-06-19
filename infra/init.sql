-- =============================================================
-- Code RAG — PostgreSQL schema
-- Runs automatically on first container start via docker-entrypoint-initdb.d
-- =============================================================

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================
-- Core table: code_chunks
-- Everything in the RAG query path reads from here.
-- =============================================================
CREATE TABLE IF NOT EXISTS code_chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id     VARCHAR(255) NOT NULL,
    file_path   TEXT NOT NULL,
    language    VARCHAR(20) NOT NULL,
    start_line  INTEGER NOT NULL,
    end_line    INTEGER NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(384) NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- HNSW index for fast cosine similarity search
-- Without this, pgvector does a full table scan on every query.
-- With it, similarity search on 100k chunks takes <50ms.
CREATE INDEX IF NOT EXISTS idx_code_chunks_embedding
    ON code_chunks USING hnsw (embedding vector_cosine_ops);

-- B-tree index for filtering by repo_id before vector search
CREATE INDEX IF NOT EXISTS idx_code_chunks_repo_id
    ON code_chunks (repo_id);

-- Composite index for repo_id + language queries
CREATE INDEX IF NOT EXISTS idx_code_chunks_repo_language
    ON code_chunks (repo_id, language);
