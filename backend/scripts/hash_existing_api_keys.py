"""One-off: hash legacy plaintext API keys in place.

Run BEFORE deploying the migration that drops the plaintext `key` column.
Usage: uv run python scripts/hash_existing_api_keys.py
"""
import asyncio
import sys
from pathlib import Path

# Ensure the backend root (parent of scripts/) is on sys.path so `app` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.security import hash_api_key
from app.features.identity.models.user import UserAPIKey


async def main() -> None:
    legacy = await UserAPIKey.filter(key_hash=None).exclude(key=None)
    for k in legacy:
        k.key_hash = hash_api_key(k.key)
        k.key_prefix = k.key[:12]
        await k.save(update_fields=["key_hash", "key_prefix"])
    print(f"hashed {len(legacy)} keys")


if __name__ == "__main__":
    asyncio.run(main())
