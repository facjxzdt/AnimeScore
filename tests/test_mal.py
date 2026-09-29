import asyncio
import time

import httpx
import pytest

from services.mal import parse_page
from services.ratings import RatingCache, RatingService


def page(identifier="56653", score="8.08", votes="16726"):
    return f'''<link rel="canonical" href="https://myanimelist.net/anime/{identifier}/Test_Anime">
        <h1 class="title-name"><strong>Test Anime</strong></h1>
        <div itemprop="aggregateRating"><span itemprop="ratingValue">{score}</span>
        <span itemprop="ratingCount">{votes}</span><meta itemprop="bestRating" content="10"></div>
        <span class="numbers ranked">Ranked <strong>#621</strong></span>
        <img itemprop="image" data-src="https://cdn.myanimelist.net/images/test.jpg">
        <p itemprop="description">Work synopsis.</p>
        <div><span class="dark_text">Episodes:</span> 13</div>
        <div><span class="dark_text">Studios:</span> <a href="/anime/producer/537/Sanzigen">Sanzigen</a></div>
        <div class="review-element"><span class="score-label">1.0</span></div>'''


def jikan(identifier="56653", score=8.08):
    return {"data": {"mal_id": int(identifier), "score": score, "scored_by": 16726, "title": "Test Anime"}}


def test_official_work_rating_and_explicit_unrated_state():
    data = parse_page(page(), "56653")
    assert data["score"] == 8.08 and data["votes"] == 16726 and data["rank"] == 621
    assert data["title"] == "Test Anime"
    assert data["details"]["poster"] == "https://cdn.myanimelist.net/images/test.jpg"
    assert data["details"]["episodes"] == 13 and data["details"]["studio"] == "Sanzigen"
    assert parse_page(page(score="N/A", votes="0"), "56653")["score"] is None


def test_real_unrated_markup_without_structured_aggregate():
    html = '''<link rel="canonical" href="https://myanimelist.net/anime/63219/Aware_Meisaku_kun">
        <h1 class="title-name">Aware! Meisaku-kun (2026)</h1>
        <div class="stats-block"><div class="fl-l score" data-title="score" data-user="- users">
        <div class="score-label score-na">N/A</div></div></div>
        <div class="review-element"><div class="score-label">9.0</div></div>'''
    result = parse_page(html, "63219")
    assert result["score"] is None and result["votes"] is None
    with pytest.raises(ValueError):
        parse_page(html.replace('class="stats-block"', 'class="review-element"'), "63219")


@pytest.mark.parametrize("html", [page("999"), "<h1>Verify your browser</h1>",
                                      page(score="NaN"), page(score="11"), page(votes="unknown"),
                                      page().replace('itemprop="ratingValue"', 'class="review-score"')])
def test_wrong_work_challenge_or_broken_rating_is_not_a_score(html):
    with pytest.raises(ValueError):
        parse_page(html, "56653")


def test_official_source_does_not_depend_on_jikan_and_coalesces_cache(tmp_path):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        assert request.url.host == "myanimelist.net"
        return httpx.Response(200, text=page())
    async def run():
        cache = RatingCache(tmp_path / "scores.db")
        cache.write("mal", "56653", {"score": None, "status": "unavailable", "updated_at": None,
                                      "retry_at": 0, "details": {}, "error": "HTTP 504", "http_status": 504})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = RatingService(cache, client, intervals={"mal": 0})
            first, second = await asyncio.gather(service.get("mal", "56653"), service.get("mal", "56653"))
            assert first == second and first["score"] == 8.08 and first["source"] == "myanimelist"
            assert "error" not in first and "http_status" not in first
            assert len(calls) == 1 and cache.read("mal", "56653")["source"] == "myanimelist"
    asyncio.run(run())


@pytest.mark.parametrize("failure", [403, 429, 503, "timeout", "challenge"])
def test_jikan_fallback_for_official_failure(tmp_path, failure):
    calls = []
    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "myanimelist.net":
            if failure == "timeout":
                raise httpx.ReadTimeout("timeout", request=request)
            return httpx.Response(200, text="<h1>Challenge</h1>") if failure == "challenge" else httpx.Response(failure)
        return httpx.Response(200, json=jikan())
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await RatingService(RatingCache(tmp_path / "scores.db"), client).get("mal", "56653")
            assert result["status"] == "ok" and result["source"] == "jikan"
            assert result["score"] == 8.08 and "error" not in result
            assert calls == ["myanimelist.net", "api.jikan.moe"]
    asyncio.run(run())


def test_unrated_official_page_is_not_replaced_with_an_old_api_score(tmp_path):
    def handler(request):
        assert request.url.host == "myanimelist.net"
        return httpx.Response(200, text=page(score="N/A", votes="0"))
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await RatingService(RatingCache(tmp_path / "scores.db"), client).get("mal", "56653")
            assert result["status"] == "no_score" and result["score"] is None
    asyncio.run(run())


def test_both_fail_preserves_stale_score_and_diagnostics(tmp_path):
    cache = RatingCache(tmp_path / "scores.db")
    timestamp = time.time() - 4000
    cache.write("mal", "56653", {"score": 8.08, "votes": 16726, "status": "ok", "updated_at": timestamp,
                                  "retry_at": 0, "source": "myanimelist", "details": {}})
    calls = []
    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(503) if request.url.host == "myanimelist.net" else httpx.Response(200, json=jikan("999"))
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = RatingService(cache, client)
            result = await service.get("mal", "56653")
            assert result["status"] == "stale" and result["score"] == 8.08 and result["updated_at"] == timestamp
            assert len(result["source_errors"]) == 2
            assert result["source_errors"][1]["error"] == "ValueError"
            assert await service.get("mal", "56653") == result
            assert len(calls) == 2
    asyncio.run(run())


def test_one_hosts_rate_limit_does_not_block_healthy_fallback(tmp_path, monkeypatch):
    calls, waits = [], []
    async def sleep(delay):
        waits.append(delay)
    monkeypatch.setattr("services.mal.asyncio.sleep", sleep)
    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "myanimelist.net":
            return httpx.Response(429, headers={"Retry-After": "120"})
        return httpx.Response(200, json=jikan(request.url.path.split("/")[-1]))
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = RatingService(RatingCache(tmp_path / "scores.db"), client)
            assert (await service.get("mal", "56653"))["status"] == "ok"
            assert (await service.get("mal", "62031"))["status"] == "ok"
            assert calls == ["myanimelist.net", "api.jikan.moe", "api.jikan.moe"]
            assert service.mal.blocked_until["myanimelist"] > time.time() + 110
            assert len(waits) == 1 and 0 < waits[0] <= 2
    asyncio.run(run())


def test_both_hosts_limited_do_not_hold_queue_or_ignore_retry_after(tmp_path):
    calls = []
    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(429, headers={"Retry-After": "120"})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = RatingService(RatingCache(tmp_path / "scores.db"), client)
            for identifier in ("56653", "62031"):
                result = await service.get("mal", identifier)
                assert result["status"] == "unavailable" and result["http_status"] == 429
                assert result["retry_at"] > time.time() + 110
            assert len(calls) == 2
    asyncio.run(run())
