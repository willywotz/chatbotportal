"""Password hashing for local accounts, backed by bcrypt.

The IdP stores only bcrypt hashes, never plaintext. bcrypt ignores input past
72 bytes, so passwords are pre-hashed with SHA-256 (hex, 64 bytes) to preserve
the full entropy of long passphrases before bcrypt runs.
"""
from __future__ import annotations

import hashlib

import bcrypt


def _prepared(password: str) -> bytes:
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("ascii")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepared(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prepared(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False
