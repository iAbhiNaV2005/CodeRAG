"""
GitHub repository fetcher.

Accepts a GitHub URL, walks the file tree, filters to code files,
downloads raw content, and optionally uploads to S3.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

import boto3
from github import Github, GithubException

from src.config import get_settings

logger = logging.getLogger(__name__)

# ── File extension → language mapping ──────────────────────────────
EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".rs": "rust",
    ".rb": "ruby",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".swift": "swift",
    ".cs": "csharp",
    ".php": "php",
    ".lua": "lua",
    ".r": "r",
    ".R": "r",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".xml": "xml",
    ".md": "markdown",
    ".toml": "toml",
}

# Directories to always skip
SKIP_DIRS: set[str] = {
    "node_modules",
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",          # Java/Rust build output
    ".gradle",
    ".idea",
    ".vscode",
    "vendor",          # Go vendor
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "coverage",
    ".nyc_output",
    "eggs",
    "*.egg-info",
}

# Max file size to download (100 KB)
MAX_FILE_SIZE_BYTES = 100_000


@dataclass
class RawFile:
    """A single fetched file from a GitHub repository."""

    path: str
    language: str
    content: str
    size: int = 0


@dataclass
class FetchResult:
    """Result of fetching an entire repository."""

    repo_id: str
    repo_url: str
    commit_hash: str
    files: list[RawFile] = field(default_factory=list)
    skipped_count: int = 0


def parse_github_url(url: str) -> tuple[str, str]:
    """
    Extract owner and repo name from a GitHub URL.

    Supports:
      - https://github.com/owner/repo
      - https://github.com/owner/repo.git
      - github.com/owner/repo
    """
    # Normalize
    url = url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]

    pattern = r"(?:https?://)?github\.com/([^/]+)/([^/]+)"
    match = re.match(pattern, url)
    if not match:
        raise ValueError(
            f"Invalid GitHub URL: {url}. "
            "Expected format: https://github.com/owner/repo"
        )
    return match.group(1), match.group(2)


def generate_repo_id(owner: str, repo_name: str, commit_hash: str) -> str:
    """Generate a deterministic repo_id from owner, repo, and commit hash."""
    short_hash = commit_hash[:12]
    return f"github_{owner}_{repo_name}_{short_hash}"


def _should_skip_path(file_path: str) -> bool:
    """Check if a file path should be skipped based on directory filters."""
    parts = PurePosixPath(file_path).parts
    for part in parts:
        if part in SKIP_DIRS:
            return True
        # Handle wildcard patterns like *.egg-info
        for skip_pattern in SKIP_DIRS:
            if "*" in skip_pattern:
                suffix = skip_pattern.replace("*", "")
                if part.endswith(suffix):
                    return True
    return False


def _get_language(file_path: str) -> str | None:
    """Get the language from a file extension. Returns None if not a code file."""
    suffix = PurePosixPath(file_path).suffix.lower()
    return EXTENSION_MAP.get(suffix)


def fetch_repo(repo_url: str, upload_to_s3: bool = True) -> FetchResult:
    """
    Fetch all code files from a GitHub repository.

    Args:
        repo_url: Full GitHub URL (e.g. https://github.com/owner/repo)
        upload_to_s3: Whether to upload raw files to S3

    Returns:
        FetchResult with all downloaded files and metadata
    """
    settings = get_settings()

    owner, repo_name = parse_github_url(repo_url)
    logger.info("Fetching repo: %s/%s", owner, repo_name)

    # Authenticate with GitHub
    gh = Github(settings.github_token) if settings.github_token else Github()

    try:
        repo = gh.get_repo(f"{owner}/{repo_name}")
    except GithubException as e:
        raise ValueError(f"Could not access repo {owner}/{repo_name}: {e}") from e

    # Get the latest commit hash from the default branch
    default_branch = repo.default_branch
    commit_hash = repo.get_branch(default_branch).commit.sha
    repo_id = generate_repo_id(owner, repo_name, commit_hash)

    logger.info(
        "Repo: %s/%s, branch: %s, commit: %s, repo_id: %s",
        owner, repo_name, default_branch, commit_hash[:12], repo_id,
    )

    # Set up S3 client if uploading
    s3_client = None
    if upload_to_s3:
        s3_kwargs = {"region_name": settings.aws_region}
        if settings.aws_endpoint_url:
            s3_kwargs["endpoint_url"] = settings.aws_endpoint_url
            s3_kwargs["aws_access_key_id"] = settings.aws_access_key_id
            s3_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        s3_client = boto3.client("s3", **s3_kwargs)

    # Walk the file tree recursively
    files: list[RawFile] = []
    skipped = 0

    def _walk_tree(contents):
        nonlocal skipped
        for content_file in contents:
            if content_file.type == "dir":
                if not _should_skip_path(content_file.path):
                    try:
                        _walk_tree(repo.get_contents(content_file.path))
                    except GithubException:
                        logger.warning("Could not read directory: %s", content_file.path)
                        skipped += 1
                continue

            # It's a file
            if _should_skip_path(content_file.path):
                skipped += 1
                continue

            language = _get_language(content_file.path)
            if language is None:
                skipped += 1
                continue

            if content_file.size and content_file.size > MAX_FILE_SIZE_BYTES:
                logger.debug("Skipping large file (%d bytes): %s", content_file.size, content_file.path)
                skipped += 1
                continue

            # Download content
            try:
                decoded = content_file.decoded_content.decode("utf-8", errors="replace")
            except (GithubException, AssertionError):
                logger.warning("Could not decode file: %s", content_file.path)
                skipped += 1
                continue

            if not decoded.strip():
                skipped += 1
                continue

            raw_file = RawFile(
                path=content_file.path,
                language=language,
                content=decoded,
                size=content_file.size or len(decoded),
            )
            files.append(raw_file)

            # Upload to S3
            if s3_client:
                s3_key = f"repos/{repo_id}/{content_file.path}"
                try:
                    s3_client.put_object(
                        Bucket=settings.s3_bucket,
                        Key=s3_key,
                        Body=decoded.encode("utf-8"),
                        ContentType="text/plain",
                    )
                except Exception as e:
                    logger.warning("Failed to upload %s to S3: %s", s3_key, e)

    try:
        root_contents = repo.get_contents("")
        _walk_tree(root_contents)
    except GithubException as e:
        raise RuntimeError(f"Failed to read repository contents: {e}") from e

    logger.info(
        "Fetched %d files, skipped %d (repo: %s)",
        len(files), skipped, repo_id,
    )

    return FetchResult(
        repo_id=repo_id,
        repo_url=repo_url,
        commit_hash=commit_hash,
        files=files,
        skipped_count=skipped,
    )
