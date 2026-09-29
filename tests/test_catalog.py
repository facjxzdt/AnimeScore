import copy
from datetime import datetime, timezone

import httpx
import pytest

from services.catalog import Catalog, CatalogRepository, CatalogUnavailable, current_season, parse_time


def test_multilingual_search_and_mapping(payload):
    catalog = Catalog(payload)
    item = catalog.search("测试别名")[0]
    assert item["name"] == "Test Anime"
    assert item["ids"] == {"bgm_id": "1", "mal_id": "2", "anilist_id": "3", "bili_id": "4"}
    assert item["sites"][0]["url"] == "https://bangumi.tv/subject/1"
    assert item["sites"][3]["url"] == "https://example.org/override"
    assert item["sites"][3]["regions"] == ["HK"]
    assert catalog.search("ＥＸＡＭＰＬＥ anime", match_mode="strict")[0]["ids"]["bgm_id"] == "1"
    assert len(catalog.search("Test Anime", match_mode="strict")) == 2
    assert catalog.search("Test", match_mode="strict") == []
    assert catalog.search("Exampl Anim", match_mode="recall")
    assert catalog.search(" ") == []
    assert catalog.search("Anime", month=7)[0]["ids"]["bgm_id"] == "5"
    assert catalog.search("Anime", anime_type="movie") == []


def test_unknown_site_and_bad_date_rejected(payload):
    payload["items"][0]["sites"][0]["site"] = "missing"
    with pytest.raises(ValueError):
        Catalog(payload)
    payload["items"][0]["sites"][0]["site"] = "bangumi"
    payload["items"][0]["begin"] = "not-a-date"
    with pytest.raises(ValueError):
        Catalog(payload)


def test_timezone_season_and_broadcast(payload):
    catalog = Catalog(payload)
    first = catalog.season(2026, "spring")[0]
    assert first["time"] == {"year": 2026, "month": 4, "day": 1, "weekday": 6}
    assert current_season(datetime(2026, 3, 31, 16, 30, tzinfo=timezone.utc)) == (2026, "spring")
    assert not catalog.season(2026, "winter")
    assert catalog.is_airing(first, parse_time("2026-05-01T00:00:00Z")) is True
    assert catalog.is_airing(first, parse_time("2026-07-02T00:00:00Z")) is False
    assert len(catalog.airing(parse_time("2026-04-02T00:00:00Z"))) == 1
    second = catalog.find("bangumi", "5")
    assert catalog.is_airing(second, parse_time("2026-07-02T00:00:00Z")) is True
    assert catalog.is_airing(second, parse_time("2027-01-02T00:00:00Z")) is None


def test_same_titles_and_unknown_ids_are_preserved(payload):
    catalog = Catalog(payload)
    assert len(catalog.entries) == 3
    assert len({item["catalog_id"] for item in catalog.entries}) == 3
    assert catalog.find("aniList", "3")["ids"]["bgm_id"] == "1"
    assert catalog.find("mal", "missing") is None
    item = catalog.find("bangumi", "1")
    item["ids"]["mal_id"] = "other"
    assert catalog.find("bangumi", "1")["ids"]["mal_id"] == "2"


def test_invalid_update_and_network_failure_keep_snapshot(tmp_path, payload, monkeypatch):
    repo = CatalogRepository(tmp_path / "data.json")
    repo.install(payload)
    original = repo.path.read_bytes()
    with pytest.raises(ValueError):
        repo.install({"items": [], "siteMeta": {}})
    assert repo.path.read_bytes() == original

    def fail(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "get", fail)
    assert repo.refresh(force=True)[0] is False
    assert repo.snapshot().find("bangumi", "1")
    assert repo.status()["last_error"]
    assert repo.path.read_bytes() == original
    repo.path.write_text("broken", encoding="utf-8")
    assert repo.snapshot().find("bangumi", "1")
    assert "failed" in repo.refresh()[1]


def test_external_replacement_refresh_and_fresh_skip(tmp_path, payload, monkeypatch):
    repo = CatalogRepository(tmp_path / "data.json")
    repo.install(payload)
    assert repo.refresh()[1] == "Local catalog is fresh"
    updated = copy.deepcopy(payload)
    updated["items"][0]["title"] = "Updated title"
    CatalogRepository(repo.path).install(updated)
    assert repo.snapshot().find("bangumi", "1")["name"] == "Updated title"
    response = httpx.Response(200, json=payload, request=httpx.Request("GET", repo.url))
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: response)
    assert repo.refresh(force=True)[0] is True
    assert repo.snapshot().find("bangumi", "1")["name"] == "Test Anime"
    assert not list(tmp_path.glob("*.tmp"))


def test_missing_catalog_reports_unavailable(tmp_path):
    repo = CatalogRepository(tmp_path / "missing.json")
    assert repo.status()["available"] is False
    with pytest.raises(CatalogUnavailable):
        repo.snapshot()
