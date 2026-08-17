"""One-off admin process: seed default data (admin account + government agencies).

15-Factor XII (admin processes): run seeding as a one-off process, not an HTTP
route. The same logic backs app startup (`app/services/seed.py`).

Usage:
    uv run python scripts/seed.py            # seed admin + agencies
    uv run python scripts/seed.py admin      # seed admin only
    uv run python scripts/seed.py agencies   # seed agencies only
"""
import asyncio
import sys
from pathlib import Path

# Ensure the backend root (parent of scripts/) is on sys.path so `app` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tortoise import Tortoise

from app.config import TORTOISE_ORM
from app.services.seed import run_seed_admin, run_seed_agencies


async def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        if target in ("all", "admin"):
            print("admin:", await run_seed_admin())
        if target in ("all", "agencies"):
            print("agencies:", await run_seed_agencies())
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(main())
