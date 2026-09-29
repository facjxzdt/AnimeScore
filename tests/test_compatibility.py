import json
import threading
import time

import httpx

from services.catalog import CatalogRepository, get_repository
from services.ratings import RatingCache, RatingService
from scripts.sync_catalog import main


def test_readers_are_not_blocked_by_refresh(tmp_path, payload, monkeypatch):
    repo = CatalogRepository(tmp_path / "data.json")
    repo.install(payload)
    downloading, finish = threading.Event(), threading.Event()

    def download(*args, **kwargs):
        downloading.set()
        assert finish.wait(timeout=2)
        return httpx.Response(200, json=payload, request=httpx.Request("GET", repo.url))

    monkeypatch.setattr(httpx, "get", download)
    worker = threading.Thread(target=repo.refresh, kwargs={"force": True})
    worker.start()
    try:
        assert downloading.wait(timeout=2)
        start = time.monotonic()
        assert repo.snapshot().find("bangumi", "1")
        assert time.monotonic() - start < 1
    finally:
        finish.set()
        worker.join(timeout=3)
    assert not worker.is_alive()


def test_offline_cli_import_and_failure_does_not_replace(client, payload, tmp_path):
    source = tmp_path / "import.json"
    payload["items"][0]["title"] = "Imported Title"
    source.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["--file", str(source)]) == 0
    assert client.get("/api/v1/anime/1?include_scores=false").json()["name"] == "Imported Title"
    source.write_text("{}", encoding="utf-8")
    assert main(["--file", str(source)]) == 1
    assert get_repository().snapshot().find("bangumi", "1")["name"] == "Imported Title"


def test_precise_mapping_uses_catalog(client):
    from utils.ext_linker import lookup_ext_ids
    assert lookup_ext_ids(bgm_id="1")["mal_id"] == "2"
    assert lookup_ext_ids(mal_id="2")["anilist_id"] == "3"
    assert lookup_ext_ids(bgm_id="unknown") is None


def test_legacy_bangumi_get_post_dependency(client, monkeypatch):
    from apis.bangumi import Bangumi

    async def search(self, query):
        return {"data": [{"id": 99, "name": "Online Title", "score": 8.8}]}

    monkeypatch.setattr(Bangumi, "search_anime_async", search)
    query = {"q": "online", "source": "bangumi"}
    response = client.post("/api/v1/search/", json=query)
    assert response.status_code == 200
    assert response.json() == client.get("/api/v1/search/", params=query).json()
    assert response.json()["results"][0]["ids"]["bgm_id"] == "99"


def test_search_live_scores_only_fetches_selected_page(client, tmp_path):
    from web_api.main import app
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, json={"rating": {"score": 9}})

    # TestClient's portal owns the same event loop as the endpoint.
    async def install_service():
        app.state.ratings = RatingService(RatingCache(tmp_path / "page.sqlite3"),
                                           httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    client.portal.call(install_service)
    try:
        response = client.get("/api/v1/search/", params={"q": "Test Anime", "offset": 1, "limit": 1, "include_scores": True})
        assert response.status_code == 200
        assert requested == ["https://api.bgm.tv/v0/subjects/5"]
        assert response.json()["results"][0]["scores"]["total"] == 9
    finally:
        client.portal.call(app.state.ratings.client.aclose)
