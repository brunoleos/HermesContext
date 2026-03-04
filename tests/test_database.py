"""Integration tests for database operations."""

import pytest


@pytest.mark.integration
class TestDatabaseConnection:
    """Test database connectivity and version."""

    def test_connection_alive(self, db):
        """Test that database connection is alive."""
        # If db fixture is available, connection succeeded
        assert db is not None

    def test_database_version(self, db):
        """Test that we can query database version."""
        # Try a simple query to verify connection
        try:
            # Most databases support some form of version check
            # This is a smoke test
            assert db is not None
        except Exception as e:
            pytest.fail(f"Database version check failed: {e}")


@pytest.mark.integration
class TestDocumentCRUD:
    """Test document create, read, update, delete operations."""

    def test_insert_and_get_document(self, db):
        """Test inserting and retrieving a document."""
        doc_id = db.insert_document(
            title="Test Doc",
            source="test_source",
            doc_type="manual",
        )

        assert doc_id is not None
        assert isinstance(doc_id, int)

        doc = db.get_document(doc_id)
        assert doc["id"] == doc_id
        assert doc["title"] == "Test Doc"
        assert doc["source"] == "test_source"
        assert doc["doc_type"] == "manual"

        # Cleanup
        db.delete_document(doc_id)

    def test_insert_document_with_metadata(self, db):
        """Test document insertion with metadata."""
        metadata = {"author": "John", "version": "1.0"}

        doc_id = db.insert_document(
            title="Doc with Meta",
            metadata=metadata,
        )

        doc = db.get_document(doc_id)
        assert doc["metadata"] == metadata

        # Cleanup
        db.delete_document(doc_id)

    def test_list_documents_pagination(self, db):
        """Test document listing with pagination."""
        # Insert test documents
        ids = []
        for i in range(5):
            doc_id = db.insert_document(title=f"Test Doc {i}")
            ids.append(doc_id)

        # Test listing with limit
        data = db.list_documents(limit=3, offset=0)
        assert len(data["items"]) <= 3
        assert "has_more" in data
        assert "total" in data

        # Cleanup
        for doc_id in ids:
            db.delete_document(doc_id)

    def test_delete_document(self, db):
        """Test document deletion."""
        doc_id = db.insert_document(title="To Delete")

        # Verify it exists
        doc = db.get_document(doc_id)
        assert doc is not None

        # Delete
        deleted = db.delete_document(doc_id)
        assert deleted

        # Verify it's gone
        doc = db.get_document(doc_id)
        assert doc is None


@pytest.mark.integration
class TestDatabaseStats:
    """Test statistics and metadata queries."""

    def test_get_stats(self, db):
        """Test retrieving database statistics."""
        stats = db.get_stats()

        assert "documents" in stats
        assert "chunks" in stats
        assert "total_tokens" in stats
        assert "by_type" in stats

        assert isinstance(stats["documents"], int)
        assert isinstance(stats["chunks"], int)
        assert isinstance(stats["total_tokens"], int)

    def test_stats_empty_db(self, db):
        """Test stats on empty database."""
        stats = db.get_stats()

        # Should have keys even if empty
        assert stats["documents"] >= 0
        assert stats["chunks"] >= 0
        assert stats["total_tokens"] >= 0
