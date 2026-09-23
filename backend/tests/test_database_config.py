"""Tests for database_url/connect_args helpers in config.py."""

from app.config import Settings, connect_args, database_url


def test_plain_url_becomes_asyncpg_scheme():
    s = Settings(DATABASE_URL="postgres://alice:secret@db.example.com:5433/mydb")
    assert database_url(s) == "postgresql+asyncpg://alice:secret@db.example.com:5433/mydb"
    assert connect_args(s) == {}


def test_sslmode_require_maps_to_ssl_connect_arg():
    s = Settings(DATABASE_URL="postgres://u:p@host:5432/db?sslmode=require")
    assert "sslmode" not in database_url(s)
    assert connect_args(s)["ssl"] == "require"


def test_sslmode_verify_full_maps_to_ssl():
    s = Settings(DATABASE_URL="postgres://u:p@host:5432/db?sslmode=verify-full")
    assert connect_args(s)["ssl"] == "verify-full"
