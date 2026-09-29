from services.catalog import get_repository


def test_search_get_post_pagination_and_ids(client):
    params = {"q": "Test Anime", "limit": 1, "offset": 1}
    get = client.get("/api/v1/search/", params=params)
    post = client.post("/api/v1/search/", json=params)
    assert get.status_code == post.status_code == 200
    assert get.json() == post.json()
    assert get.json()["total"] == 2
    assert len(get.json()["results"]) == 1
    assert get.json()["source"] == "bangumi-data"
    result = client.get("/api/v1/search/", params={"q": "测试动画"}).json()["results"][0]
    assert result["ids"]["anilist_id"] == "3"
    assert result["scores"]["total"] is None
    assert result["data_source"] == "bangumi-data"


def test_catalog_season_detail_export_consistency(client):
    status = client.get("/api/v1/catalog/").json()
    assert status["available"] and status["total"] == 3
    assert status["source"]["license"] == "CC BY 4.0"
    assert client.get("/api/v1/health/").json()["status"] == "ok"
    season = client.get("/api/v1/anime/season/2026/spring").json()
    assert season["total"] == 1
    detail = client.get("/api/v1/anime/1?include_scores=false")
    assert detail.status_code == 200
    assert detail.json()["time"]["month"] == 4
    assert client.get("/api/v1/anime/unknown?include_scores=false").status_code == 404
    exported = client.get("/api/v1/export/json?type=all").json()
    assert exported["total"] == client.get("/api/v1/stats/").json()["total_anime"] == 3
    listed = client.get("/api/v1/anime/?limit=1&offset=1&sort_by=time").json()
    assert listed["total"] == 3 and len(listed["items"]) == 1
    assert client.get("/api/v1/export/csv?type=all").text.startswith("\ufeffname,")


def test_errors_do_not_become_500(client):
    for params in ({"q": "test", "source": "unknown"}, {"q": " "}, {"q": "test", "month": 13}):
        assert client.get("/api/v1/search/", params=params).status_code == 422
    assert client.post("/api/v1/search/", json={"q": "test", "source_type": "manga"}).status_code == 400
    assert client.get("/api/v1/anime/airing?sort_by=invalid").status_code == 422
    assert client.get("/api/v1/search/?q=nomatch").json()["total"] == 0
    assert client.get("/api/v1/export/json?type=invalid").status_code == 422


def test_missing_dataset_degrades_health_but_not_liveness(client):
    repository = get_repository()
    repository.path.unlink()
    repository._catalog = None
    assert client.get("/api/v1/health/").json()["status"] == "degraded"
    assert client.get("/api/v1/health/ping").status_code == 200
    assert client.get("/api/v1/search/?q=test").status_code == 503
    assert client.get("/api/v1/anime/airing").status_code == 503
