import asyncio
import copy
from datetime import datetime, timezone

import httpx
import pytest

from services.analytics import AnalyticsStore, DEFAULT_WEIGHTS, rank_items
from services.catalog import Catalog, CatalogRepository
from services.collector import Collector
from services.ratings import RatingCache, RatingService, weighted_score


def observed(item, timestamp, scores=None):
    item = copy.deepcopy(item)
    item["scores"] = scores or {"bgm": 8, "mal": 9, "anilist": 7}
    item["votes"] = {"bgm": 100, "mal": 200, "anilist": 300}
    item["score_status"] = {p: {"status": "ok", "updated_at": datetime.fromtimestamp(timestamp, timezone.utc).isoformat()} for p in item["scores"]}
    return item


def test_custom_weight_normalization_and_missing_platform():
    assert weighted_score({"bgm": 8, "mal": 9, "anilist": 7}, DEFAULT_WEIGHTS) == 8.286
    assert weighted_score({"bgm": 8, "mal": 9, "anilist": 7}, dict.fromkeys(DEFAULT_WEIGHTS, 1)) == 8
    assert weighted_score({"bgm": 8, "mal": None}, {"bgm": 5, "mal": 2}) == 8
    assert weighted_score({"bgm": 8}, {"bgm": 0, "mal": 2}) is None


def test_real_history_no_backfill_and_weight_recalculation(tmp_path, payload):
    store = AnalyticsStore(RatingCache(tmp_path / "test.sqlite3"))
    anime = Catalog(payload).entries[0]
    now = 1780000000
    assert store.history(anime, "1y", DEFAULT_WEIGHTS, now)["points"] == []
    first = observed(anime, now)
    store.record([first], now)
    store.record([first], now + 3600)
    data = store.history(anime, "7d", DEFAULT_WEIGHTS, now + 3600)
    assert len(data["points"]) == 1
    assert data["points"][0]["scores"]["total"] == 8.286
    data = store.history(anime, "7d", dict.fromkeys(DEFAULT_WEIGHTS, 1), now + 3600)
    assert data["points"][0]["scores"]["total"] == 8
    second = observed(anime, now + 7200)
    second["score_status"]["mal"]["status"] = "stale"
    store.record([second], now + 7200)
    history = store.history(anime, "7d", DEFAULT_WEIGHTS, now + 7200)
    assert len(history["points"]) == 2
    assert history["points"][-1]["scores"]["mal"] is None
    assert history["points"][-1]["votes"]["mal"] is None


def test_windows_daily_aggregation_and_retention(tmp_path, payload):
    store = AnalyticsStore(RatingCache(tmp_path / "test.sqlite3"))
    anime = Catalog(payload).entries[0]
    start = 1780012800  # UTC midnight
    for offset in (0, 3600, 86400, 10 * 86400):
        store.record([observed(anime, start + offset)], start + offset)
    assert len(store.history(anime, "7d", DEFAULT_WEIGHTS, start + 10 * 86400)["points"]) == 1
    assert len(store.history(anime, "30d", DEFAULT_WEIGHTS, start + 10 * 86400)["points"]) == 4
    assert len(store.history(anime, "90d", DEFAULT_WEIGHTS, start + 10 * 86400)["points"]) == 3
    store.record([], start + 420 * 86400)
    assert store.history(anime, "1y", DEFAULT_WEIGHTS, start + 420 * 86400)["points"] == []


def test_lease_and_hourly_schedule_across_workers(tmp_path):
    cache = RatingCache(tmp_path / "test.sqlite3")
    first, second = AnalyticsStore(cache), AnalyticsStore(cache)
    owner = first.claim(now=1000)
    assert owner
    assert second.claim(now=1100) is None
    assert second.claim(now=1100, force=True) is None
    assert first.progress(owner, 4, 10, 1, now=1200)
    assert second.claim(now=1400) is None
    first.finish(owner, now=1400)
    assert second.claim(now=4599) is None
    assert second.claim(now=4600)
    assert not first.progress(owner, 9, 10, 1, now=4601)


def test_expired_lease_recovers(tmp_path):
    store = AnalyticsStore(RatingCache(tmp_path / "test.sqlite3"))
    old = store.claim(now=1000)
    new = store.claim(now=1301)
    assert new and new != old
    store.finish(old, now=1400)
    assert store.claim(now=1500) is None


def test_ranking_custom_weights_ties_and_filters(payload):
    items = Catalog(payload).entries
    first = observed(items[0], 1, {"bgm": 8, "mal": 9, "anilist": 7})
    second = observed(items[1], 1, {"bgm": 9, "mal": 7, "anilist": 9})
    assert rank_items([first, second], DEFAULT_WEIGHTS)[0]["ids"]["bgm_id"] == "5"
    assert rank_items([first, second], {"bgm": 0, "mal": 1, "anilist": 0})[0]["ids"]["bgm_id"] == "1"
    second["scores"] = first["scores"].copy()
    assert [item["rank"] for item in rank_items([first, second], DEFAULT_WEIGHTS)] == [1, 1]
    assert rank_items([first], DEFAULT_WEIGHTS, min_votes=1000) == []


def test_hourly_collector_records_metadata_and_tracks(tmp_path, payload, monkeypatch):
    monkeypatch.setenv("SCORE_AUTO_UPDATE", "1")
    monkeypatch.setattr('services.collector.current_season', lambda: (2026, 'spring'))
    repository = CatalogRepository(tmp_path / "catalog.json")
    repository.install(payload)
    cache = RatingCache(tmp_path / "ratings.sqlite3")
    store = AnalyticsStore(cache)
    store.track(repository.snapshot().entries[1]["catalog_id"])

    def handler(request):
        if request.url.host == "api.bgm.tv":
            return httpx.Response(200, json={"rating": {"score": 8, "total": 123, "rank": 25}, "images": {"large": "https://example.org/poster.jpg"}, "summary": "Plot"})
        if request.url.host == "api.jikan.moe":
            return httpx.Response(200, json={"data": {"mal_id": 2, "score": 9, "scored_by": 200}})
        return httpx.Response(200, json={"data": {"Media": {"meanScore": 80, "averageScore": 90, "stats": {"scoreDistribution": [{"score": 80, "amount": 300}]}}}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = RatingService(cache, client, intervals=dict.fromkeys(DEFAULT_WEIGHTS, 0))
            collector = Collector(repository, service)
            assert await collector.run_once()
            assert not await collector.run_once()
            assert collector.store.status()["completed"] == 2
            assert collector.store.status()["observations"] == 2
            assert cache.read("bgm", "1")["votes"] == 123
            assert cache.read("anilist", "3")["votes"] == 300
    asyncio.run(run())


def test_dashboard_endpoints_validation_and_export(client):
    rank = client.get('/api/v1/dashboard/ranking?year=2026&season=spring').json()
    assert rank['total'] == 1
    item = rank['items'][0]
    assert item['rank'] is None
    cid = item['catalog_id']
    for period in ('7d', '30d', '90d', '1y'):
        response = client.get(f'/api/v1/dashboard/anime/{cid}/history?period={period}')
        assert response.status_code == 200
        assert response.json()['points'] == []
    assert client.get(f'/api/v1/dashboard/anime/{cid}?refresh=false').status_code == 200
    assert client.get(f'/api/v1/dashboard/anime/{cid}/history.csv').text.startswith('\ufefftimestamp_utc')
    assert client.get('/api/v1/dashboard/status').json()['enabled'] is False
    for query in ('bgm=0&mal=0&anilist=0', 'bgm=-1', 'bgm=nan', 'anilist=101'):
        assert client.get(f'/api/v1/dashboard/ranking?{query}').status_code == 422
    assert client.get('/api/v1/dashboard/anime/unknown/history').status_code == 404
