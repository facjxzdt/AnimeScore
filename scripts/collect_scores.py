"""Manually run the same leased collection as the hourly background task."""

import asyncio
import json

import httpx

from services.catalog import get_repository
from services.collector import Collector
from services.ratings import RatingCache, RatingService


async def main():
    async with httpx.AsyncClient(timeout=10, follow_redirects=True,
                                 headers={"User-Agent": "facjxzdt/AnimeScore (manual score collection)"}) as client:
        collector = Collector(get_repository(), RatingService(RatingCache(), client))
        completed = await collector.run_once(force=True)
        status = collector.store.status()
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0 if completed and not status["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
