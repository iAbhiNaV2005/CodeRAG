"""
Unit tests for the code chunker.

These tests are deterministic — no external services needed.
"""

import pytest

from src.chunker import CodeChunk, chunk_file, _compute_line_range
from src.fetcher import RawFile


class TestComputeLineRange:
    """Tests for the line range computation utility."""

    def test_single_line_at_start(self):
        full = "line one\nline two\nline three"
        start, end, pos = _compute_line_range(full, "line one", 0)
        assert start == 1
        assert end == 1

    def test_multiline_chunk(self):
        full = "line one\nline two\nline three\nline four"
        chunk = "line two\nline three"
        start, end, pos = _compute_line_range(full, chunk, 0)
        assert start == 2
        assert end == 3

    def test_chunk_at_end(self):
        full = "a\nb\nc\nd\ne"
        chunk = "d\ne"
        start, end, pos = _compute_line_range(full, chunk, 0)
        assert start == 4
        assert end == 5


class TestChunkFile:
    """Tests for the file chunking logic."""

    def test_small_file_single_chunk(self):
        raw = RawFile(
            path="src/hello.py",
            language="python",
            content='def hello():\n    print("Hello, world!")\n',
            size=40,
        )
        chunks = chunk_file(raw, "test_repo_123")
        assert len(chunks) >= 1
        assert all(isinstance(c, CodeChunk) for c in chunks)
        assert chunks[0].repo_id == "test_repo_123"
        assert chunks[0].file_path == "src/hello.py"
        assert chunks[0].language == "python"

    def test_large_file_multiple_chunks(self):
        # Create a file large enough to produce multiple chunks
        lines = [f"def function_{i}():\n    x = {i}\n    return x\n\n" for i in range(100)]
        content = "".join(lines)

        raw = RawFile(
            path="src/big_module.py",
            language="python",
            content=content,
            size=len(content),
        )
        chunks = chunk_file(raw, "test_repo_456")
        assert len(chunks) > 1

        # Verify line ranges are sequential and non-overlapping at start_line
        for i in range(1, len(chunks)):
            assert chunks[i].start_line >= chunks[i - 1].start_line

    def test_empty_file_no_chunks(self):
        raw = RawFile(path="empty.py", language="python", content="", size=0)
        chunks = chunk_file(raw, "test_repo")
        assert chunks == []

    def test_javascript_chunking(self):
        raw = RawFile(
            path="src/app.js",
            language="javascript",
            content=(
                "const express = require('express');\n"
                "const app = express();\n\n"
                "app.get('/', (req, res) => {\n"
                "    res.send('Hello');\n"
                "});\n\n"
                "module.exports = app;\n"
            ),
            size=150,
        )
        chunks = chunk_file(raw, "test_repo")
        assert len(chunks) >= 1
        assert chunks[0].language == "javascript"
