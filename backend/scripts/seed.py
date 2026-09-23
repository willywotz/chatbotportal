"""One-off admin process: seed default data (government agencies).

15-Factor XII (admin processes): run seeding as a one-off process, not an HTTP
route. The same logic backs app startup (`app/services/seed.py`).

Usage:
    uv run python scripts/seed.py            # seed agencies
    uv run python scripts/seed.py agencies   # seed agencies (explicit)
"""
import asyncio
import sys
from pathlib import Path

# Ensure the backend root (parent of scripts/) is on sys.path so `app` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.features.agency.services.seed import run_seed_agencies


async def main() -> None:
    print("agencies:", await run_seed_agencies())


if __name__ == "__main__":
    asyncio.run(main())
