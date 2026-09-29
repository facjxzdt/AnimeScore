import asyncio
import time

import httpx
import pytest

from services.catalog import Catalog
from services.ratings import RatingCache, RatingService, aggregate, merge_ratings, numeric_score


@pytest.mark.parametrize("value", [None, "None", "N/A", "Error", "NaN", float("inf"), -1, 0, 11, True])
def test_invalid_or_unrated_score(value):
    assert numeric_score(value) is None


def test_weight_normalization():
    assert aggregate({"bgm": 8, "mal": 9}) == pytest.approx(8.286)
    assert aggregate({"bgm": 8.5}) == 8.5
    assert aggregate({}) is None
    assert numeric_score(85, 100) == 8.5


def test_fetch_by_id_partial_failure_and_cache(tmp_path, payload):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.host == "api.bgm.tv":
            assert request.url.path == "/v0/subjects/1"
            return httpx.Response(200, json={"rating": {"score": 8}})
        if request.url.host in {"api.jikan.moe", "myanimelist.net"}:
            return httpx.Response(503)
        return httpx.Response(200, json={"data": {"Media": {"meanScore": 80, "averageScore": 90}}})

    async def run():
        cache = RatingCache(tmp_path / "ratings.db")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = RatingService(cache, client, intervals=dict.fromkeys(("bgm", "mal", "anilist"), 0))
            item = Catalog(payload).find("bangumi", "1")
            first, second = await asyncio.gather(service.enrich([item]), service.enrich([item]))
            assert len(calls) == 4
            assert first == second
            assert first[0]["scores"] == {"bgm": 8, "mal": None, "anilist": 8.5, "total": 8}
            assert first[0]["score_status"]["mal"]["status"] == "unavailable"
            assert RatingCache(cache.path).read("bgm", "1")["score"] == 8

    asyncio.run(run())


def test_failure_preserves_stale_rating_and_missing_ids_skip_network(tmp_path, payload):
    cache = RatingCache(tmp_path / "ratings.db")
    cache.write("bgm", "1", {"score": 9, "status": "ok", "updated_at": time.time() - 4000, "retry_at": 0})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(429))) as client:
            service = RatingService(cache, client, intervals=dict.fromkeys(("bgm", "mal", "anilist"), 0))
            item = Catalog(payload).find("bangumi", "1")
            item["ids"] = {"bgm_id": "1"}
            result = (await service.enrich([item]))[0]
            assert result["scores"]["bgm"] == 9
            assert result["score_status"]["bgm"]["status"] == "stale"
            assert result["score_status"]["mal"]["status"] == "unmapped"
            assert cache.read("bgm", "1")["score"] == 9
            assert "total" not in item["scores"]

    asyncio.run(run())


def test_cache_identity_is_not_title(tmp_path, payload):
    entries = Catalog(payload).entries
    merged = merge_ratings(entries[1], {("bgm", "1"): {"score": 9}})
    assert merged["scores"]["total"] is None
    assert merged["score_status"]["bgm"]["status"] == "not_fetched"


def test_rate_limit_cooldown_applies_to_next_id(tmp_path, monkeypatch):
    waits = []
    calls = []

    async def fake_sleep(delay):
        waits.append(delay)

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "120"})
        return httpx.Response(200, json={"data": {"Media": {"meanScore": 80}}})

    monkeypatch.setattr("services.ratings.asyncio.sleep", fake_sleep)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = RatingService(RatingCache(tmp_path / "test.db"), client)
            limited = await service.get("anilist", "1")
            assert limited["http_status"] == 429
            assert limited["retry_at"] > time.time() + 110
            assert await service.get("anilist", "1") == limited
            assert len(calls) == 1
            assert (await service.get("anilist", "2"))["score"] == 8
            assert len(waits) == 1 and waits[0] > 110

    asyncio.run(run())
