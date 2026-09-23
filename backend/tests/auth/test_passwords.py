"""bcrypt password hashing round-trips and rejects wrong / malformed input."""
from __future__ import annotations

from app.auth.oidc.passwords import hash_password, verify_password


def test_hash_verifies_correct_password():
    h = hash_password("s3cret-pass")
    assert verify_password("s3cret-pass", h)


def test_hash_rejects_wrong_password():
    h = hash_password("s3cret-pass")
    assert not verify_password("wrong", h)


def test_hash_is_salted_and_not_plaintext():
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2
    assert "same" not in h1


def test_long_passphrase_beyond_72_bytes_is_distinct():
    base = "a" * 80
    assert verify_password(base, hash_password(base))
    assert not verify_password("a" * 79 + "b", hash_password(base))


def test_verify_tolerates_malformed_hash():
    assert not verify_password("x", "not-a-bcrypt-hash")
