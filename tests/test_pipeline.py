"""Integration tests for RAG pipeline (ingest, search, cleanup)."""

import pytest


@pytest.mark.integration
class TestIngestAndSearch:
    """Test complete ingest → search → verify pipeline."""

    def test_ingest_and_search_basic(self, engine, cleanup_docs):
        """Test basic ingest and search workflow."""
        title = "Test Document"
        content = "This is a test document about machine learning and artificial intelligence."

        # Ingest
        result = engine.ingest_document(
            title=title,
            content=content,
            source="test",
            doc_type="test",
        )

        assert result["document_id"] is not None
        assert result["chunk_count"] > 0
        cleanup_docs.append(result["document_id"])

        # Search for related content
        search_result = engine.search(
            query="machine learning",
            top_k=5,
            use_reranker=True,
        )

        assert len(search_result["results"]) > 0
        assert search_result["results"][0]["document_id"] == result["document_id"]

    def test_ingest_empty_content(self, engine):
        """Test that empty content returns zero chunks."""
        result = engine.ingest_document(
            title="Empty Doc",
            content="",
            source="test",
        )

        assert result["document_id"] is not None
        assert result["chunk_count"] == 0

    def test_ingest_whitespace_only(self, engine):
        """Test that whitespace-only content returns zero chunks."""
        result = engine.ingest_document(
            title="Whitespace Doc",
            content="   \n\t  \n  ",
            source="test",
        )

        assert result["document_id"] is not None
        assert result["chunk_count"] == 0

    def test_ingest_with_metadata(self, engine, cleanup_docs):
        """Test document ingestion with metadata."""
        result = engine.ingest_document(
            title="Doc with Meta",
            content="Some content here",
            metadata={"author": "test", "version": "1.0"},
        )

        cleanup_docs.append(result["document_id"])

        # Retrieve and verify metadata
        doc = engine.db.get_document(result["document_id"])
        assert doc["metadata"]["author"] == "test"
        assert doc["metadata"]["version"] == "1.0"

    def test_search_without_reranker(self, engine, cleanup_docs):
        """Test search with reranking disabled."""
        title = "Test Doc"
        content = "Oracle database administration guide"

        result = engine.ingest_document(title=title, content=content)
        cleanup_docs.append(result["document_id"])

        search_result = engine.search(
            query="Oracle administration",
            top_k=5,
            use_reranker=False,
        )

        assert "results" in search_result
        assert len(search_result["results"]) > 0

    def test_search_with_reranker(self, engine, cleanup_docs):
        """Test search with reranking enabled."""
        title = "Test Doc"
        content = "Oracle database administration and configuration"

        result = engine.ingest_document(title=title, content=content)
        cleanup_docs.append(result["document_id"])

        search_result = engine.search(
            query="Oracle setup",
            top_k=5,
            use_reranker=True,
        )

        assert "results" in search_result
        assert len(search_result["results"]) > 0
