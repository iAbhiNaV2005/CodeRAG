"""
Language-aware code chunker.

Uses LangChain's RecursiveCharacterTextSplitter with language-specific
separators to produce semantically meaningful code chunks with line
number tracking.
"""

import logging
from dataclasses import dataclass

from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from src.config import get_settings
from src.fetcher import RawFile

logger = logging.getLogger(__name__)

# ── Map our language strings to LangChain Language enum ──────────
LANGCHAIN_LANGUAGE_MAP: dict[str, Language] = {
    "python": Language.PYTHON,
    "javascript": Language.JS,
    "typescript": Language.TS,
    "java": Language.JAVA,
    "go": Language.GO,
    "cpp": Language.CPP,
    "c": Language.C,
    "rust": Language.RUST,
    "ruby": Language.RUBY,
    "kotlin": Language.KOTLIN,
    "scala": Language.SCALA,
    "swift": Language.SWIFT,
    "csharp": Language.CSHARP,
    "php": Language.PHP,
    "lua": Language.LUA,
    "html": Language.HTML,
    "markdown": Language.MARKDOWN,
    # Note: Language.SQL does not exist in langchain-text-splitters 1.x
    # SQL files fall back to generic RecursiveCharacterTextSplitter
}


@dataclass
class CodeChunk:
    """A single chunk of code with full metadata for storage."""

    repo_id: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    content: str


def _compute_line_range(full_text: str, chunk_text: str, search_start: int = 0) -> tuple[int, int, int]:
    """
    Compute the start_line and end_line for a chunk within the full file text.

    Args:
        full_text: The complete file content.
        chunk_text: The chunk's text content.
        search_start: Character index to start searching from (to handle duplicates).

    Returns:
        (start_line, end_line, char_position) — 1-indexed line numbers and the
        character position where the chunk was found.
    """
    pos = full_text.find(chunk_text, search_start)
    if pos == -1:
        # Fallback: if exact match fails (due to splitter normalization),
        # use the search_start position
        pos = search_start

    # Count newlines before this position to get 1-indexed start line
    start_line = full_text[:pos].count("\n") + 1

    # Count newlines within the chunk to get end line
    end_line = start_line + chunk_text.count("\n")

    return start_line, end_line, pos + len(chunk_text)


def chunk_file(raw_file: RawFile, repo_id: str) -> list[CodeChunk]:
    """
    Split a single file into code chunks using language-aware splitting.

    Args:
        raw_file: The raw file to chunk.
        repo_id: Repository identifier to attach to each chunk.

    Returns:
        List of CodeChunk objects with line numbers and metadata.
    """
    settings = get_settings()

    # Get LangChain language enum, or fall back to generic splitting
    lc_language = LANGCHAIN_LANGUAGE_MAP.get(raw_file.language)

    if lc_language:
        splitter = RecursiveCharacterTextSplitter.from_language(
            language=lc_language,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
    else:
        # Fallback: generic text splitting for languages without LangChain support
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            separators=["\n\n", "\n", " ", ""],
        )

    # Split the content
    text_chunks = splitter.split_text(raw_file.content)

    if not text_chunks:
        return []

    # Build CodeChunk objects with accurate line ranges
    chunks: list[CodeChunk] = []
    search_pos = 0

    for text in text_chunks:
        start_line, end_line, search_pos = _compute_line_range(
            raw_file.content, text, search_pos - settings.chunk_overlap if search_pos > 0 else 0
        )

        chunks.append(
            CodeChunk(
                repo_id=repo_id,
                file_path=raw_file.path,
                language=raw_file.language,
                start_line=start_line,
                end_line=end_line,
                content=text,
            )
        )

    logger.debug(
        "Chunked %s → %d chunks (language: %s)",
        raw_file.path, len(chunks), raw_file.language,
    )

    return chunks


def chunk_files(raw_files: list[RawFile], repo_id: str) -> list[CodeChunk]:
    """
    Chunk all files from a fetched repository.

    Args:
        raw_files: List of raw files from the fetcher.
        repo_id: Repository identifier.

    Returns:
        Flat list of all CodeChunk objects across all files.
    """
    all_chunks: list[CodeChunk] = []

    for raw_file in raw_files:
        try:
            file_chunks = chunk_file(raw_file, repo_id)
            all_chunks.extend(file_chunks)
        except Exception as e:
            logger.warning("Failed to chunk %s: %s", raw_file.path, e)

    logger.info(
        "Total chunks: %d from %d files (repo: %s)",
        len(all_chunks), len(raw_files), repo_id,
    )

    return all_chunks
