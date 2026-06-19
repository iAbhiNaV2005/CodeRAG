# Code RAG

RAG-powered code Q&A system: paste a GitHub URL, ask questions about the codebase, get answers grounded in actual source code with file-path citations.

## Architecture

```
Next.js UI → Spring Boot Gateway (JWT + Rate Limit) → FastAPI (RAG Pipeline)
                                                          ↓
                                                   PostgreSQL (pgvector)
                                                   DynamoDB (repos, sessions)
                                                   S3 (raw files)
```

## Project Structure

```
RAG/
├── rag-pipeline/    # Python — FastAPI + RAG logic
├── gateway/         # Java — Spring Boot gateway (Phase 3)
├── frontend/        # Next.js app (Phase 4)
└── infra/           # Docker Compose, SQL migrations, deploy scripts
```

## Quick Start (Phase 1 — CLI)

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- GitHub Personal Access Token
- Google AI API key (for Gemini 1.5 Flash)

### 1. Start infrastructure

```bash
cd infra
docker compose up -d
```

This starts:
- PostgreSQL 16 with pgvector extension (port 5432)
- LocalStack with S3 + DynamoDB (port 4566)

### 2. Set up Python environment

```bash
cd rag-pipeline
python -m venv venv
venv\Scripts\activate          # Windows
pip install -e ".[dev]"
```

### 3. Configure environment

```bash
copy .env.example .env
# Edit .env with your actual keys:
#   GITHUB_TOKEN=ghp_...
#   GOOGLE_API_KEY=AI...
```

### 4. Ingest a repository

```bash
python -m src ingest https://github.com/expressjs/express
```

### 5. Ask questions

```bash
# Single question
python -m src query <repo_id> "How does the routing system work?"

# Interactive chat (multi-turn)
python -m src chat <repo_id>
```

## Running Tests

```bash
cd rag-pipeline
pytest tests/ -v
```
