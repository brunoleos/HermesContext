"""Shared test fixtures and configuration."""

import pytest

from src.database import Database
from src.embeddings import EmbeddingService
from src.engine import RAGEngine


@pytest.fixture(scope="session")
def db():
    """Database fixture with real connection (for integration tests).

    Creates schema and yields database instance.
    Auto-closes after all tests.
    """
    database = Database()
    database.connect()
    database.init_schema()
    yield database
    database.close()


@pytest.fixture(scope="session")
def engine(db):
    """RAG Engine fixture with real dependencies.

    Uses session-scoped database and embeddings service.
    """
    emb = EmbeddingService()
    return RAGEngine(db=db, emb=emb)


@pytest.fixture
def cleanup_docs(db):
    """Fixture to cleanup test documents after each test.

    Yields a list to append document IDs to,
    then deletes them all after test completes.
    """
    doc_ids = []
    yield doc_ids
    for doc_id in doc_ids:
        try:
            db.delete_document(doc_id)
        except Exception:
            pass
