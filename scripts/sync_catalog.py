"""Run with python -m scripts.sync_catalog; supports offline imports."""

import argparse
import asyncio
import json
from pathlib import Path

import httpx

from services.catalog import SEASONS, CatalogUnavailable, current_season, get_repository
from services.ratings import RatingCache, RatingService


async def refresh_scores(items):
    async with httpx.AsyncClient(timeout=10, follow_redirects=True,
                                 headers={"User-Agent": "facjxzdt/AnimeScore (catalog score refresh)"}) as client:
        service = RatingService(RatingCache(), client)
        results = []
        # Bound queued work as well as per-provider network concurrency.
        for start in range(0, len(items), 10):
            results.extend(await service.enrich(items[start:start + 10]))
        return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Sync the bangumi-data catalog and optionally fetch seasonal ratings")
    parser.add_argument("--file", type=Path, help="Import a local upstream dist/data.json instead of downloading")
    parser.add_argument("--force", action="store_true", help="Refresh the catalog even when its cache is fresh")
    parser.add_argument("--scores", action="store_true", help="Fetch ratings for the selected season")
    parser.add_argument("--year", type=int)
    parser.add_argument("--season", choices=SEASONS)
    args = parser.parse_args(argv)
    if (args.year is None) != (args.season is None):
        parser.error("--year and --season must be supplied together")
    repository = get_repository()
    try:
        if args.file:
            count = repository.install(json.loads(args.file.read_text(encoding="utf-8")))
            print(f"Imported {count} catalog entries")
        else:
            _, message = repository.refresh(force=args.force)
            print(message)
            if repository.last_error:
                return 1
        catalog = repository.snapshot()
        if args.scores:
            year, season = (args.year, args.season) if args.year else current_season()
            items = catalog.season(year, season)
            result = asyncio.run(refresh_scores(items))
            rated = sum(item["scores"].get("total") is not None for item in result)
            failed = sum(state["status"] in {"unavailable", "stale"} for item in result for state in item["score_status"].values())
            print(f"{year} {season}: {rated}/{len(items)} entries rated; {failed} provider requests degraded")
            if failed:
                return 1
        return 0
    except (CatalogUnavailable, OSError, ValueError) as exc:
        print(f"Sync failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
