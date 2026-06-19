"""
FastAPI application factory.

Creates the FastAPI app with all routers, CORS, and lifespan events.
Run with: uvicorn src.api.app:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.models import HealthResponse

# Load .env before anything else
load_dotenv()

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App startup and shutdown events."""
    logger.info("Code RAG API starting up...")

    # Pre-load the embedding model on startup so first request isn't slow
    from src.embedder import _get_model
    _get_model()
    logger.info("Embedding model pre-loaded.")

    yield

    logger.info("Code RAG API shutting down...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Code RAG API",
        description="RAG-powered code Q&A service. Ingest GitHub repos and ask questions about them.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS -- allow all origins in dev, lock down in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    from src.api.routers.ingest import router as ingest_router
    from src.api.routers.chat import router as chat_router

    app.include_router(ingest_router)
    app.include_router(chat_router)

    # Health check
    @app.get("/health", response_model=HealthResponse, tags=["Health"])
    async def health():
        return HealthResponse()

    return app


# Module-level app instance for uvicorn
app = create_app()
