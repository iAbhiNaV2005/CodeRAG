"""
Unit tests for the GitHub fetcher.

Tests URL parsing and file filtering logic (deterministic, no API calls).
"""

import pytest

from src.fetcher import parse_github_url, generate_repo_id, _should_skip_path, _get_language


class TestParseGithubUrl:
    """Tests for GitHub URL parsing."""

    def test_standard_https(self):
        owner, repo = parse_github_url("https://github.com/torvalds/linux")
        assert owner == "torvalds"
        assert repo == "linux"

    def test_with_dot_git(self):
        owner, repo = parse_github_url("https://github.com/torvalds/linux.git")
        assert owner == "torvalds"
        assert repo == "linux"

    def test_trailing_slash(self):
        owner, repo = parse_github_url("https://github.com/owner/repo/")
        assert owner == "owner"
        assert repo == "repo"

    def test_without_protocol(self):
        owner, repo = parse_github_url("github.com/owner/repo")
        assert owner == "owner"
        assert repo == "repo"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Invalid GitHub URL"):
            parse_github_url("https://gitlab.com/owner/repo")

    def test_empty_url_raises(self):
        with pytest.raises(ValueError):
            parse_github_url("")


class TestGenerateRepoId:
    """Tests for deterministic repo ID generation."""

    def test_basic(self):
        rid = generate_repo_id("torvalds", "linux", "abc123def456789")
        assert rid == "github_torvalds_linux_abc123def456"

    def test_deterministic(self):
        rid1 = generate_repo_id("a", "b", "hash12345678")
        rid2 = generate_repo_id("a", "b", "hash12345678")
        assert rid1 == rid2


class TestShouldSkipPath:
    """Tests for directory/file filtering."""

    def test_skip_node_modules(self):
        assert _should_skip_path("node_modules/package/index.js") is True

    def test_skip_git(self):
        assert _should_skip_path(".git/config") is True

    def test_skip_pycache(self):
        assert _should_skip_path("src/__pycache__/module.cpython-311.pyc") is True

    def test_allow_normal_path(self):
        assert _should_skip_path("src/utils/parser.py") is False

    def test_skip_venv(self):
        assert _should_skip_path("venv/lib/python3.11/site.py") is True


class TestGetLanguage:
    """Tests for file extension → language mapping."""

    def test_python(self):
        assert _get_language("src/app.py") == "python"

    def test_javascript(self):
        assert _get_language("lib/index.js") == "javascript"

    def test_typescript(self):
        assert _get_language("src/app.tsx") == "typescript"

    def test_unknown_extension(self):
        assert _get_language("data.csv") is None

    def test_no_extension(self):
        assert _get_language("Makefile") is None

    def test_java(self):
        assert _get_language("com/example/App.java") == "java"
