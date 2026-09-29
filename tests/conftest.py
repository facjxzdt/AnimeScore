import copy
import json

import pytest
from fastapi.testclient import TestClient

from services.catalog import get_repository
from web_api.api_v1.deps import get_score_cache


@pytest.fixture
def payload():
    first = {
        "title": "Test Anime", "titleTranslate": {"zh-Hans": ["测试动画", "测试别名"], "en": ["Example Anime"]},
        "type": "tv", "lang": "ja", "officialSite": "https://example.org/",
        "begin": "2026-03-31T16:30:00Z", "end": "2026-07-01T15:00:00Z",
        "broadcast": "R/2026-04-03T16:00:00Z/P7D",
        "sites": [{"site": "bangumi", "id": "1"}, {"site": "mal", "id": "2"},
                  {"site": "aniList", "id": "3"},
                  {"site": "bilibili", "id": "4", "url": "https://example.org/override", "regions": ["HK"]}],
    }
    second = copy.deepcopy(first)
    second.update(title="Test Anime", begin="2026-07-01T00:00:00Z", end="", broadcast="",
                  titleTranslate={"en": ["Test Anime Season 2"]}, sites=[{"site": "bangumi", "id": "5"}])
    third = copy.deepcopy(first)
    third.update(title="Unknown Date", begin="", end="", broadcast="", sites=[], titleTranslate={})
    return {
        "siteMeta": {
            "bangumi": {"title": "Bangumi", "urlTemplate": "https://bangumi.tv/subject/{{id}}", "type": "info"},
            "mal": {"title": "MAL", "urlTemplate": "https://myanimelist.net/anime/{{id}}", "type": "info"},
            "aniList": {"title": "AniList", "urlTemplate": "https://anilist.co/anime/{{id}}", "type": "info"},
            "bilibili": {"title": "Bilibili", "urlTemplate": "https://www.bilibili.com/md{{id}}", "type": "onair", "regions": ["CN"]},
        },
        "items": [first, second, third],
    }


@pytest.fixture
def client(tmp_path, monkeypatch, payload):
    monkeypatch.setattr('dotenv.load_dotenv', lambda *args, **kwargs: False)
    for name in ('BGM_CLIENT_ID', 'BGM_CLIENT_SECRET', 'BGM_REDIRECT_URI', 'BGM_ADMIN_IDS', 'LLM_BASE_URL', 'LLM_API_KEY', 'LLM_MODEL', 'ANIMESCORE_ADMIN_TOKEN'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('FILMARKS_AUTO_MAP', '0')
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("BANGUMI_DATA_PATH", str(path))
    monkeypatch.setenv("BANGUMI_DATA_AUTO_UPDATE", "0")
    monkeypatch.setenv("SCORE_AUTO_UPDATE", "0")
    monkeypatch.setenv("SCORE_CACHE_PATH", str(tmp_path / "ratings.sqlite3"))
    get_repository.cache_clear()
    get_score_cache.cache_clear()
    from web_api.main import app
    with TestClient(app) as test_client:
        yield test_client
    get_repository.cache_clear()
    get_score_cache.cache_clear()
