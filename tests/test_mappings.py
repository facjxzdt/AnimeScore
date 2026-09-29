import asyncio
import copy
import json
import time

import httpx
import pytest

from services.analytics import AnalyticsStore, DEFAULT_WEIGHTS
from services.catalog import Catalog
from services.mappings import MappingConflict, MappingStore
from services.providers import normalize_id
from services.ratings import RatingCache, RatingService, merge_ratings
from services.scrapers import parse_rating

FILMARKS = '<h1>Test Season</h1><script type="application/ld+json">{"@type":"TVSeason","title":"Test Season","aggregateRating":{"ratingValue":"4.2","bestRating":"5","reviewCount":"157"}}</script><div class="p-mark-histogram__total-count">1,940件のレビュー</div><div class="c2-rating-s__text">1.0</div>'


@pytest.mark.parametrize('provider,value,expected', [
    ('filmarks', 'https://filmarks.com/animes/1431/6089', '1431/6089'),
    ('anikore', 'https://www.anikore.jp/anime/14266/', '14266'),
    ('bgm', 'https://bangumi.tv/subject/501963', '501963'),
    ('mal', 'https://myanimelist.net/anime/59193/Example', '59193'),
    ('anilist', '178789', '178789'),
])
def test_normalize_work_url(provider, value, expected):
    assert normalize_id(provider, value) == expected


@pytest.mark.parametrize('value', ['123', '../123/45', '0/12', 'https://localhost/animes/12/34',
                                        'https://filmarks.com@evil.example/animes/12/34', 'https://filmarks.com/animes/12/34/reviews/5',
                                        'https://filmarks.com:443/animes/12/34', 'https://filmarks.com/animes/12/34/../../'])
def test_reject_wrong_seasons_and_arbitrary_urls(value):
    with pytest.raises(ValueError):
        normalize_id('filmarks', value)


def test_work_level_scores_not_review_scores_or_popularity():
    data = parse_rating('filmarks', FILMARKS)
    assert data['score'] == 8.4 and data['votes'] == 1940
    assert data['title'] == 'Test Season'
    data = parse_rating('anikore', '<h1>Test Anime</h1><div>総合得点 99.2</div><div class="l-animeDetailHeader_pointAndButtonBlock_starBlock"><strong>3.8</strong><span>(201)</span></div>')
    assert data['score'] == 7.6 and data['votes'] == 201
    with pytest.raises(ValueError):
        parse_rating('anikore', '<h1>Access challenge</h1>Request 4.2 pending')
    with pytest.raises(ValueError):
        parse_rating('filmarks', '<div class="c2-rating-s__text">4.7</div>')


def test_overrides_survive_catalog_refresh_and_are_reversible(tmp_path, payload):
    cache = RatingCache(tmp_path / 'test.db')
    store = MappingStore(cache)
    catalog = Catalog(payload)
    first = catalog.entries[0]
    initial = copy.deepcopy(first)
    store.save(first, {'filmarks': {'mode': 'manual', 'id': 'https://filmarks.com/animes/1431/6089', 'note': 'confirmed season'},
                       'mal': {'mode': 'disabled'}}, 0, catalog.entries)
    mapped = store.apply([first])[0]
    assert mapped['ids']['filmarks_id'] == '1431/6089'
    assert 'mal_id' not in mapped['ids']
    assert first == initial
    updated = copy.deepcopy(payload)
    updated['items'][0]['title'] = 'Updated upstream title'
    newer = Catalog(updated).entries[0]
    assert newer['catalog_id'] != first['catalog_id']
    assert store.apply([newer])[0]['ids']['filmarks_id'] == '1431/6089'
    detail = store.save(newer, {'mal': {'mode': 'catalog'}, 'filmarks': {'mode': 'catalog'}}, 1, Catalog(updated).entries)
    assert detail['item']['ids']['mal_id'] == '2'
    assert detail['overrides'] == {}
    assert len(detail['audit']) == 2


def test_conflicts_are_atomic_and_do_not_overwrite_other_anime(tmp_path, payload):
    store = MappingStore(RatingCache(tmp_path / 'test.db'))
    catalog = Catalog(payload)
    first, second = catalog.entries[:2]
    store.save(first, {'filmarks': {'mode': 'manual', 'id': '1/2'}}, 0, catalog.entries)
    with pytest.raises(MappingConflict):
        store.save(first, {'filmarks': {'mode': 'manual', 'id': '1/3'}}, 0, catalog.entries)
    with pytest.raises(MappingConflict):
        store.save(second, {'filmarks': {'mode': 'manual', 'id': '1/2'}}, 0, catalog.entries)
    with pytest.raises(MappingConflict):
        store.save(second, {'bgm': {'mode': 'manual', 'id': '1'}}, 0, catalog.entries)
    assert store.detail(first)['overrides']['filmarks']['id'] == '1/2'
    assert store.detail(second)['revision'] == 0


def test_mapping_corrections_do_not_relabel_old_history(tmp_path, payload):
    cache = RatingCache(tmp_path / 'test.db')
    store, history = MappingStore(cache), AnalyticsStore(cache)
    catalog = Catalog(payload)
    item = catalog.entries[0]
    now = round(time.time(), 6)
    ratings = {('bgm', '1'): {'score': 8, 'status': 'ok', 'updated_at': now},
               ('mal', '2'): {'score': 9, 'status': 'ok', 'updated_at': now}}
    history.record([merge_ratings(store.apply([item])[0], ratings)], now)
    result = store.save(item, {'bgm': {'mode': 'manual', 'id': '99'}}, 0, catalog.entries)['item']
    data = history.history(result, '7d', DEFAULT_WEIGHTS, now)
    assert len(data['points']) == 1
    assert data['points'][0]['scores']['bgm'] is None
    assert data['points'][0]['scores']['mal'] == 9
    assert data['points'][0]['scores']['total'] == 9


def test_new_providers_use_effective_ids_and_cache_access_failures(tmp_path, payload):
    cache = RatingCache(tmp_path / 'test.db')
    catalog = Catalog(payload)
    item = catalog.entries[2]
    MappingStore(cache).save(item, {'filmarks': {'mode': 'manual', 'id': '1/2'}, 'anikore': {'mode': 'manual', 'id': '3'}}, 0, catalog.entries)
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, text=FILMARKS) if request.url.host == 'filmarks.com' else httpx.Response(202, text='Challenge')
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = RatingService(cache, client, intervals={'filmarks': 0, 'anikore': 0})
            first = (await service.enrich([item]))[0]
            assert first['scores']['filmarks'] == 8.4
            assert first['score_status']['anikore']['status'] == 'unavailable'
            assert first['score_status']['anikore']['http_status'] == 202
            await service.enrich([item])
            assert len(calls) == 2
            assert 'https://filmarks.com/animes/1/2' in calls
    asyncio.run(run())


def test_admin_auth_validation_edit_export_and_coverage(client, monkeypatch):
    monkeypatch.setenv('ANIMESCORE_ADMIN_TOKEN', 'test-admin-token')
    assert client.get('/api/v1/admin/status').status_code == 401
    headers = {'Authorization': 'Bearer test-admin-token'}
    assert client.get('/api/v1/admin/status', headers={**headers, 'Origin': 'https://evil.example'}).status_code == 403
    assert len(client.get('/api/v1/admin/status', headers=headers).json()['providers']) == 5
    result = client.get('/api/v1/admin/mappings?q=测试动画&missing=filmarks', headers=headers).json()
    cid = result['items'][0]['catalog_id']
    update = {'revision': 0, 'changes': {'filmarks': {'mode': 'manual', 'id': '1431/6089', 'note': 'Confirmed'}}}
    assert client.put(f'/api/v1/admin/mappings/{cid}', json=update).status_code == 401
    response = client.put(f'/api/v1/admin/mappings/{cid}', json=update, headers=headers)
    assert response.status_code == 200
    assert response.json()['revision'] == 1
    assert response.json()['filmarks_match']['status'] == 'unchecked'
    assert client.put(f'/api/v1/admin/mappings/{cid}', json=update, headers=headers).status_code == 409
    assert client.get('/api/v1/admin/mappings?edited=true', headers=headers).json()['total'] == 1
    assert len(client.get('/api/v1/admin/mappings/export', headers=headers).json()['items']) == 1
    detail = client.get(f'/api/v1/dashboard/anime/{cid}?refresh=false').json()
    assert detail['ids']['filmarks_id'] == '1431/6089'
    for query in ['bgm=0&mal=0&anilist=0&filmarks=1', 'min_platforms=5']:
        assert client.get('/api/v1/dashboard/ranking?' + query).status_code == 200
    monkeypatch.delenv('ANIMESCORE_ADMIN_TOKEN')
    assert client.get('/api/v1/admin/status').status_code == 403
