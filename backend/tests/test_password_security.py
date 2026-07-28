from app.auth.security import hash_password, verify_password


def test_verify_password_rejects_unusable_hash():
    # Anonymous users store hashed_password="!" (never authenticates); a
    # malformed/non-bcrypt hash must fail closed, not raise.
    assert verify_password("anything", "!") is False


def test_verify_password_accepts_correct_password():
    assert verify_password("pw12345", hash_password("pw12345")) is True


def test_verify_password_rejects_wrong_password():
    assert verify_password("wrong", hash_password("pw12345")) is False
