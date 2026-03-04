"""Unit tests for configuration."""

import os

import pytest

from src.config import Settings


class TestSettings:
    """Test Settings configuration loading from environment."""

    def test_default_values(self):
        """Settings should have sensible defaults."""
        # Create fresh settings (using defaults)
        settings = Settings()

        assert settings.embedding_model == "BAAI/bge-m3"
        assert settings.reranker_model == "cross-encoder/ms-marco-MiniLM-L-6-v2"
        assert settings.chunk_size == 512
        assert settings.chunk_overlap == 64
        assert settings.mcp_port == 9090

    def test_env_var_override(self, monkeypatch):
        """Settings should override defaults from environment variables."""
        monkeypatch.setenv("EMBEDDING_MODEL", "custom-model")
        monkeypatch.setenv("MCP_PORT", "5000")

        settings = Settings()

        assert settings.embedding_model == "custom-model"
        assert settings.mcp_port == 5000

    def test_redis_url_default(self):
        """Redis URL should have default."""
        settings = Settings()
        assert settings.redis_url == "redis://localhost:6379"

    def test_oracle_settings(self, monkeypatch):
        """Oracle settings should come from environment."""
        monkeypatch.setenv("ORACLE_DSN", "test.db")
        monkeypatch.setenv("ORACLE_USER", "testuser")

        settings = Settings()

        assert settings.oracle_dsn == "test.db"
        assert settings.oracle_user == "testuser"
