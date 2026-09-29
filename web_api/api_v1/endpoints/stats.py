"""Statistics computed from the same catalog/cache view as the list APIs."""

from collections import Counter

from fastapi import APIRouter, Query

from services.catalog import get_repository
from web_api.api_v1 import schemas
from web_api.api_v1.deps import get_airing_items, get_subscribed_items

router = APIRouter()


@router.get("/", response_model=schemas.StatsInfo)
def get_stats():
    repository = get_repository()
    entries = repository.snapshot().entries
    airing = get_airing_items()
    distribution = Counter()
    for item in airing:
        score = item["scores"].get("total")
        if score is not None:
            distribution[f"{min(int(score), 9)}-{min(int(score), 9) + 1}"] += 1
    return schemas.StatsInfo(
        total_anime=len(entries), airing_count=len(airing), subscribed_count=len(get_subscribed_items()),
        score_distribution=dict(distribution),
        year_distribution=dict(Counter(str(item["time"]["year"]) for item in entries if item["time"])),
        last_updated=repository.status()["updated_at"],
    )


@router.get("/score-distribution")
def get_score_distribution():
    distribution = Counter(round(item["scores"]["total"] * 2) / 2 for item in get_airing_items()
                           if item["scores"].get("total") is not None)
    return {"distribution": dict(sorted(distribution.items())), "total": sum(distribution.values())}


@router.get("/studio-ranking")
def get_studio_ranking(limit: int = Query(10, ge=1, le=100)):
    # bangumi-data has no studio field; never infer one from the title.
    studios = {}
    for item in get_airing_items():
        if item.get("studio"):
            studios.setdefault(item["studio"], []).append(item["scores"].get("total"))
    return {"by_count": [
        {"studio": studio, "count": len(scores),
         "avg_score": round(sum(rated) / len(rated), 2) if (rated := [s for s in scores if s is not None]) else None}
        for studio, scores in sorted(studios.items(), key=lambda pair: len(pair[1]), reverse=True)[:limit]
    ]}
