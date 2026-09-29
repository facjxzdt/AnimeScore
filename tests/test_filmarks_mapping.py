import asyncio
import copy
import json
import time

import httpx
import pytest

from services.catalog import CatalogRepository
from services.filmarks_mapping import FilmarksMapper, evaluate, parse_listing, parse_work, title_key
from services.filmarks_jobs import FilmarksJobs
from services.mappings import MappingConflict, MappingStore
from services.ratings import RatingCache, RatingService


def listing(entries, more=False):
    return '<h1 class="c-heading-1">Results</h1>' + ''.join(
        f'<div class="p-content-cassette"><h3 class="p-content-cassette__title">{title}</h3>'
        f'<div class="p-content-cassette__other-info">公開日：{day}</div><a href="/animes/{identifier}">Details</a>'
        f'<a href="/animes/{identifier}/reviews/999">Wrong review</a></div>' for identifier, title, day in entries
    ) + ('<a rel="next" href="?page=2">Next</a>' if more else '')


def work(identifier='1/2', title='Test Anime', day='2026-04-02', related=''):
    data = {'@type': 'TVSeason', 'title': title, 'releaseDate': day, 'seasonNumber': 5,
            'aggregateRating': {'ratingValue': 4, 'bestRating': 5, 'ratingCount': 200}}
    return f'<link rel="canonical" href="https://filmarks.com/animes/{identifier}"><script type="application/ld+json">{json.dumps(data)}</script>{related}'


def setup(tmp_path, payload, handler):
    repository = CatalogRepository(tmp_path / 'catalog.json')
    repository.install(payload)
    cache = RatingCache(tmp_path / 'scores.db')
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    mapper = FilmarksMapper(repository, RatingService(cache, client, intervals={'filmarks': 0}))
    return mapper, client, repository.snapshot().entries[0]


def test_titles_dates_and_sequels_preserve_identity():
    assert title_key('無職転生Ⅲ') == title_key('無職転生 III')
    assert title_key('Example 第二期') == title_key('Example 2nd Season')
    assert title_key('闇芝居 十七期') == title_key('闇芝居 第17期')
    assert title_key('Example シーズン4') == title_key('Example Season 4')
    assert title_key('Example 第2クール') != title_key('Example 第1クール')
    item = {'name': '無職転生Ⅲ', 'begin': '2026-07-14', 'type': 'tv'}
    candidate = {'id': '1431/6089', 'title': '無職転生 III', 'date': '2026-07-05', 'verified': True}
    assert evaluate(item, candidate)['eligible']
    assert not evaluate(item, {**candidate, 'title': '無職転生 II'})['eligible']
    assert not evaluate(item, {**candidate, 'date': '2024-07-05'})['eligible']
    assert not evaluate(item, {**candidate, 'date': None})['eligible']
    assert not evaluate(item, {**candidate, 'verified': False})['eligible']


def test_parsers_extract_work_links_and_reject_wrong_work_or_challenge():
    result = parse_listing(listing([('1/2', 'Test Anime', '2026年04月02日')], more=True))
    assert result['items'][0]['id'] == '1/2' and result['items'][0]['date'] == '2026-04-02'
    assert result['has_next'] and len(result['items']) == 1
    data = parse_work(work(related='<a href="/animes/1/3">Test Anime 2</a><a href="/animes/9/8">Unrelated</a>'), '1/2')
    assert data['rating']['score'] == 8 and data['verified']
    assert [value['id'] for value in data['related']] == ['1/3']
    for call in (lambda: parse_work(work('2/3'), '1/2'), lambda: parse_listing('<h1>Access denied</h1>')):
        with pytest.raises(ValueError):
            call()


def test_listing_handles_cards_without_anchor_links():
    html = '''<div class="p-content-cassette" @click="onClickDetailLink($event, '/animes/4918/7134')">
      <h3 class="p-content-cassette__title">SEALOOK 2nd season</h3>
      <div class="p-content-cassette__other-info">公開日：2026年07月01日</div>
      <a href="/animes/4918/7134/reviews/999">Review</a></div>'''
    result = parse_listing(html)
    assert result['items'][0]['id'] == '4918/7134'
    assert result['items'][0]['title'] == 'SEALOOK 2nd season'
    for invalid in ('https://other.example/animes/1/2', '/animes/1/2/reviews/999'):
        assert not parse_listing(html.replace('/animes/4918/7134\'', invalid + "'"))['items']


def test_shared_season_label_does_not_match_unrelated_series():
    item = {'name': 'SEALOOK 2nd season', 'begin': '2026-07-01'}
    unrelated = {'id': '1/2', 'title': '幼女戦記 II', 'date': '2026-07-01', 'verified': True}
    assert evaluate(item, unrelated)['similarity'] < 0.48
    assert not evaluate(item, unrelated)['eligible']
    assert evaluate(item, {**unrelated, 'title': 'SEALOOK 第二期'})['eligible']


def test_verified_unique_match_auto_saves_and_reuses_pages(tmp_path, payload):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, text=work() if '/animes/' in request.url.path else listing([('1/2', 'Test Anime', '2026年04月02日')]))
    mapper, client, item = setup(tmp_path, payload, handler)
    async def run():
        async with client:
            result = await mapper.discover(item, apply=True)
            assert result['status'] == 'applied' and result['applied_id'] == '1/2'
            detail = mapper.store.detail(item)
            assert detail['item']['mapping_sources']['filmarks'] == 'auto'
            assert detail['overrides']['filmarks']['source'] == 'auto' and len(detail['audit']) == 1
            assert mapper.cache.read('filmarks', '1/2')['score'] == 8
            mapper.store.save(item, {'mal': {'mode': 'disabled'}}, detail['revision'], mapper.repository.snapshot().entries)
            assert mapper.store.detail(item)['overrides']['filmarks']['source'] == 'auto'
            assert (await mapper.discover(item, apply=True))['status'] == 'skipped'
            await mapper.discover(item, force=True)
            assert len(calls) == 2
    asyncio.run(run())


def test_ambiguous_same_title_is_reviewed_not_auto_saved(tmp_path, payload):
    def handler(request):
        if '/animes/' in request.url.path:
            return httpx.Response(200, text=work(request.url.path.removeprefix('/animes/')))
        return httpx.Response(200, text=listing([('1/2', 'Test Anime', '2026年04月02日'), ('1/3', 'Test Anime', '2026年04月03日')]))
    mapper, client, item = setup(tmp_path, payload, handler)
    async def run():
        async with client:
            result = await mapper.discover(item, apply=True)
            assert result['status'] == 'review' and len(result['candidates']) == 2
            assert not mapper.store.detail(item)['overrides']
    asyncio.run(run())


def test_search_alias_then_related_season_resolves_correct_work(tmp_path, payload):
    data = copy.deepcopy(payload)
    data['items'][0]['title'] = 'Example II'
    data['items'][0]['titleTranslate'] = {}
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if '/release_year/' in request.url.path:
            return httpx.Response(200, text=listing([]))
        if request.url.path == '/search/animes':
            return httpx.Response(200, text=listing([('1/2', 'Example', '2024年04月02日')]))
        if request.url.path == '/animes/1/2':
            return httpx.Response(200, text=work('1/2', 'Example', '2024-04-02', '<a href="/animes/1/3">Example 第二期</a>'))
        return httpx.Response(200, text=work('1/3', 'Example 第二期'))
    mapper, client, item = setup(tmp_path, data, handler)
    async def run():
        async with client:
            result = await mapper.discover(item, apply=True)
            assert result['status'] == 'applied' and result['applied_id'] == '1/3'
            assert '同系列作品' in result['methods']
    asyncio.run(run())


@pytest.mark.parametrize('status', [404, 410])
def test_missing_season_falls_back_to_search_and_caches_absence(tmp_path, payload, status):
    data = copy.deepcopy(payload)
    data['items'][0]['begin'] = '1943-04-02T00:00:00Z'
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if '/release_year/' in request.url.path:
            return httpx.Response(status)
        if request.url.path == '/search/animes':
            return httpx.Response(200, text=listing([('1/2', 'Test Anime', '1943年04月02日')]))
        return httpx.Response(200, text=work(day='1943-04-02'))
    mapper, client, item = setup(tmp_path, data, handler)
    async def run():
        async with client:
            result = await mapper.discover(item, apply=True)
            assert result['status'] == 'applied' and result['applied_id'] == '1/2'
            assert result['errors'] == [] and '别名检索' in result['methods']
            assert mapper.cache.read('filmarks', '1/2')['score'] == 8
            season_path = '/list-anime/release_year/1943/4'
            assert calls.count(season_path) == 1
            restarted = FilmarksMapper(mapper.repository, mapper.ratings)
            assert (await restarted.discover(item, force=True))['status'] == 'matched'
            assert calls.count(season_path) == 1
            with mapper.cache.connect() as db:
                db.execute('UPDATE filmarks_pages SET updated_at=? WHERE key LIKE ?',
                           (time.time() - 86401, '%' + season_path))
            await restarted.discover(item, force=True)
            assert calls.count(season_path) == 2
    asyncio.run(run())


def test_missing_season_and_empty_search_is_not_found(tmp_path, payload):
    def handler(request):
        if '/release_year/' in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, text=listing([]))
    mapper, client, item = setup(tmp_path, payload, handler)
    async def run():
        async with client:
            result = await mapper.discover(item, apply=True)
            assert result['status'] == 'not_found' and result['errors'] == []
            assert '别名检索' in result['methods']
            assert not mapper.store.detail(item)['overrides']
    asyncio.run(run())


@pytest.mark.parametrize('path,status', [('/search/animes', 404), ('/animes/1/2', 404),
                                       ('/list-anime/release_year/2026/4', 500)])
def test_missing_search_or_work_and_server_errors_remain_visible(tmp_path, payload, path, status):
    def handler(request):
        if request.url.path == path:
            return httpx.Response(status)
        entries = [('1/2', 'Test Anime', '2026年04月02日')] if path == '/animes/1/2' else []
        return httpx.Response(200, text=listing(entries))
    mapper, client, item = setup(tmp_path, payload, handler)
    async def run():
        async with client:
            result = await mapper.discover(item, apply=True)
            assert result['status'] in {'error', 'review'} and result['errors']
            assert not mapper.store.detail(item)['overrides']
            assert mapper.cache.read('filmarks', '1/2') is None
    asyncio.run(run())


def test_manual_disable_and_concurrent_manual_edits_are_protected(tmp_path, payload):
    mapper, client, item = setup(tmp_path, payload, lambda _: httpx.Response(500))
    mapper.store.save(item, {'filmarks': {'mode': 'disabled'}}, 0, mapper.repository.snapshot().entries)
    async def run():
        async with client:
            assert (await mapper.discover(item, apply=True))['status'] == 'skipped'
    asyncio.run(run())
    with pytest.raises(MappingConflict):
        mapper.store.save(item, {'filmarks': {'mode': 'manual', 'id': '1/2'}}, 1, mapper.repository.snapshot().entries, source='auto')
    assert mapper.store.detail(item)['item']['mapping_sources']['filmarks'] == 'disabled'


@pytest.mark.parametrize('status', [403, 429])
def test_access_limit_is_error_and_sets_cooldown(tmp_path, payload, status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={'Retry-After': '600'})
    mapper, client, item = setup(tmp_path, payload, handler)
    async def run():
        async with client:
            result = await mapper.discover(item, apply=True)
            assert result['status'] == 'error' and result['errors']
            assert len(calls) == 1
            assert mapper.ratings.blocked_until['filmarks'] > time.time() + 590
    asyncio.run(run())


def test_jobs_are_leased_cancelable_and_resume_saved_cursor(tmp_path, payload):
    mapper, client, item = setup(tmp_path, payload, lambda _: httpx.Response(200, text=listing([])))
    jobs = FilmarksJobs(mapper)
    entries = mapper.repository.snapshot().entries
    jobs.start(entries, limit=2)
    with pytest.raises(MappingConflict):
        jobs.start(entries)
    owner, state = jobs._claim()
    assert owner and jobs._claim()[0] is None
    state['completed'] = 1
    jobs._progress(owner, state, 'queued')
    new_owner, resumed = jobs._claim()
    assert new_owner != owner and resumed['completed'] == 1
    jobs._progress(new_owner, resumed, 'queued')
    jobs.cancel()
    async def run():
        async with client:
            assert await jobs.run_once()
            assert jobs.status()['status'] == 'cancelled'
            assert jobs.status()['completed'] == 1
    asyncio.run(run())


def test_mapping_job_api_is_authenticated_and_validated(client, monkeypatch):
    monkeypatch.setenv('ANIMESCORE_ADMIN_TOKEN', 'test-token')
    headers = {'Authorization': 'Bearer test-token'}
    assert client.get('/api/v1/admin/filmarks/job').status_code == 401
    assert client.post('/api/v1/admin/filmarks/job', json={'limit': 999}, headers=headers).status_code == 422
    assert client.post('/api/v1/admin/filmarks/job', json={'scope': 'season', 'year': 2026, 'season': 'spring'}, headers=headers).status_code == 200
    assert client.post('/api/v1/admin/filmarks/job', json={}, headers=headers).status_code == 409
    assert client.post('/api/v1/admin/filmarks/job/cancel', headers=headers).json()['cancel_requested']
