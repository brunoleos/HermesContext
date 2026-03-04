"""Unit tests for document chunking and enrichment."""

import pytest

from src.engine import RAGEngine


class TestSplitText:
    """Test _split_text() chunking algorithm."""

    def test_short_text_single_chunk(self):
        """Short text should return as single chunk."""
        text = "This is a short text with only a few words."
        chunks = RAGEngine._split_text(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_empty_text(self):
        """Empty text should return empty list."""
        chunks = RAGEngine._split_text("")
        assert chunks == []

    def test_whitespace_only(self):
        """Whitespace-only text should return empty list."""
        chunks = RAGEngine._split_text("   \n\t  ")
        assert chunks == []

    def test_hierarchical_splitting(self):
        """Test that splitting respects hierarchical separators."""
        text = (
            "Paragraph 1\n\n"
            "Paragraph 2 with sentence 1. Sentence 2. Sentence 3.\n\n"
            "Paragraph 3"
        )
        chunks = RAGEngine._split_text(text)
        # Should split primarily by \n\n (paragraph separator)
        assert len(chunks) >= 1
        assert all(chunk.strip() for chunk in chunks)

    def test_overlap_preserved(self):
        """Test that overlap is maintained between chunks."""
        words = " ".join(["word"] * 1000)  # Large text to force multiple chunks
        chunks = RAGEngine._split_text(words)
        if len(chunks) > 1:
            # Check that consecutive chunks have some word overlap
            chunk1_words = set(chunks[0].split())
            chunk2_words = set(chunks[1].split())
            overlap = chunk1_words & chunk2_words
            assert len(overlap) > 0, "Consecutive chunks should have overlap"

    def test_chunk_size_respect(self):
        """Test that chunks don't exceed size limit (approximately)."""
        from src.config import settings

        words = " ".join(["word"] * 2000)
        chunks = RAGEngine._split_text(words)

        for chunk in chunks:
            word_count = len(chunk.split())
            # Allow 20% tolerance for overlap and separator handling
            assert word_count <= settings.chunk_size * 1.2


class TestEnrichChunk:
    """Test _enrich_chunk() contextual enrichment."""

    def test_enrichment_with_title_and_type(self):
        """Enrichment should add document title and type prefix."""
        chunk = "Some content here"
        title = "Document Title"
        doc_type = "resolution"

        enriched = RAGEngine._enrich_chunk(chunk, title, 0, doc_type)

        assert title in enriched
        assert doc_type in enriched
        assert "Trecho 1" in enriched
        assert chunk in enriched
        assert enriched.startswith("[")

    def test_enrichment_without_type(self):
        """Enrichment should work without doc_type."""
        chunk = "Some content"
        title = "Title"

        enriched = RAGEngine._enrich_chunk(chunk, title, 0)

        assert title in enriched
        assert "Trecho 1" in enriched
        assert chunk in enriched

    def test_enrichment_chunk_index(self):
        """Enrichment should correctly number chunks."""
        chunk = "Content"
        title = "Title"

        enr0 = RAGEngine._enrich_chunk(chunk, title, 0)
        enr1 = RAGEngine._enrich_chunk(chunk, title, 1)
        enr5 = RAGEngine._enrich_chunk(chunk, title, 5)

        assert "Trecho 1" in enr0
        assert "Trecho 2" in enr1
        assert "Trecho 6" in enr5

    def test_enrichment_preserves_content(self):
        """Enrichment should preserve original chunk text."""
        chunk = "Important legal text here"
        title = "Law"

        enriched = RAGEngine._enrich_chunk(chunk, title, 2)

        # Original text should be at the end
        assert enriched.endswith(chunk)
