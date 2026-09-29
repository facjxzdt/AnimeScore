"""Run a bounded, resumable Filmarks mapping batch using the shared job lease."""

import argparse
import asyncio
import json

import httpx

from services.catalog import SEASONS, current_season, get_repository
from services.filmarks_jobs import FilmarksJobs
from services.filmarks_mapping import FilmarksMapper
from services.ratings import RatingCache, RatingService


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=current_season()[0])
    parser.add_argument("--season", choices=SEASONS, default=current_season()[1])
    parser.add_argument("--all", action="store_true", help="Process missing mappings across the catalog")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--review-only", action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-evaluate cached candidate decisions")
    args = parser.parse_args()
    if not 1 <= args.limit <= 250:
        parser.error("--limit must be between 1 and 250")
    repository = get_repository()
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "facjxzdt/AnimeScore (Filmarks mapping)"}) as client:
        mapper = FilmarksMapper(repository, RatingService(RatingCache(), client))
        jobs = FilmarksJobs(mapper)
        if jobs.status()["status"] not in {"queued", "running"}:
            items = repository.snapshot().entries if args.all else repository.snapshot().season(args.year, args.season)
            matches = mapper.results()
            items = sorted(items, key=lambda item: matches.get(item["catalog_id"], {}).get("checked_at", 0))
            jobs.start(items, apply=not args.review_only, force=args.force, limit=args.limit)
        while jobs.status()["status"] in {"queued", "running"}:
            await jobs.run_once()
            state = jobs.status()
            print(json.dumps(state, ensure_ascii=False), flush=True)
            if state["status"] in {"queued", "running"}:
                await asyncio.sleep(5)
        print(json.dumps(jobs.status(), ensure_ascii=False, indent=2))
        return 1 if jobs.status()["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
