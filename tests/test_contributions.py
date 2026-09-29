import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import HTTPException

from services.auth import SESSION_COOKIE
from services.catalog import CatalogRepository
from services.contributions import Contributions, today
from services.llm_review import ModelReviewer
from services.ratings import RatingCache, RatingService

USER = {'id': 71, 'username': 'verified-user'}


def setup(tmp_path, monkeypatch, payload):
    monkeypatch.setenv('LLM_BASE_URL', 'https://model.example/v1')
    monkeypatch.setenv('LLM_API_KEY', 'private-model-key')
    monkeypatch.setenv('LLM_MODEL', 'mapping-model')
    repository = CatalogRepository(tmp_path / 'catalog.json')
    repository.install(payload)
    calls = {'model': 0, 'site': 0, 'verdict': 'match', 'confidence': 0.99, 'bad_json': False, 'unavailable': False}
    def handler(request):
        if request.url.host == 'model.example':
            calls['model'] += 1
            body = json.loads(request.content)
            assert request.headers['authorization'] == 'Bearer private-model-key'
            assert USER['username'] not in request.content.decode() and 'private-bgm-token' not in request.content.decode()
            assert body['max_tokens'] == 800 and len(body['messages']) == 2
            if calls['unavailable']:
                return httpx.Response(503, text='private-model-key internal error')
            verdict = {'verdict': calls['verdict'], 'confidence': calls['confidence'], 'reason': '对应同一动画季度' if calls['verdict'] == 'match' else '季度不同或依据不足',
                       'checks': {'title': calls['verdict'] == 'match', 'season': calls['verdict'] == 'match', 'format': True}}
            if calls.get('extra_id'):
                verdict['id'] = '99/99'
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': 'not json' if calls['bad_json'] else json.dumps(verdict)}}]})
        calls['site'] += 1
        if calls.get('site_unavailable'):
            return httpx.Response(503, text='Service unavailable')
        identifier = calls.get('canonical_id') or request.url.path.removeprefix('/animes/')
        data = {'@type': 'TVSeason', 'title': 'Test Anime', 'releaseDate': '2026-04-01', 'aggregateRating': {'ratingValue': 4, 'bestRating': 5, 'ratingCount': 123}}
        html = f'<link rel="canonical" href="https://filmarks.com/animes/{identifier}"><script type="application/ld+json">{json.dumps(data)}</script>'
        return httpx.Response(200, text=html)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ratings = RatingService(RatingCache(tmp_path / 'scores.db'), client, intervals={'filmarks': 0})
    service = Contributions(repository, ratings)
    return service, client, repository.snapshot().entries[0], calls


def advance(service):
    with service.cache.connect() as db:
        db.execute('UPDATE contributions SET created_at=created_at-31')


def test_accepted_submission_atomically_saves_credit_fetches_score_and_records_history(tmp_path, monkeypatch, payload):
    service, client, item, calls = setup(tmp_path, monkeypatch, payload)
    result = service.submit(USER, item, 'filmarks', 'https://filmarks.com/animes/1/2')
    assert result['status'] == 'queued'
    async def run():
        async with client:
            assert await service.run_once()
            assert service.get(result['id'])['status'] == 'accepted'
            detail = service.mappings.detail(item)
            assert detail['item']['ids']['filmarks_id'] == '1/2'
            assert detail['item']['mapping_sources']['filmarks'] == 'community'
            assert detail['item']['mapping_contributors']['filmarks']['username'] == USER['username']
            assert service.quota(USER['id'])['remaining'] == 5
            assert await service.run_once()
            assert service.get(result['id'])['score_status'] == 'ok'
            assert service.cache.read('filmarks', '1/2')['score'] == 8
            history = service.analytics.history(detail['item'], '7d', {'filmarks': 1})
            assert history['points'][-1]['scores']['filmarks'] == 8
            assert calls['model'] == 1
            assert not await service.run_once()
    asyncio.run(run())
    saved = service.mappings.save(item, {'filmarks': {'mode': 'manual', 'id': '1/2', 'note': 'edited note'}}, 1, service.repository.snapshot().entries)
    assert saved['item']['mapping_contributors']['filmarks']['username'] == USER['username']
    changed = service.mappings.save(item, {'filmarks': {'mode': 'manual', 'id': '1/3'}}, 2, service.repository.snapshot().entries)
    assert not changed['item']['mapping_contributors']


def test_five_wrong_attempts_block_further_model_calls_and_reset_in_beijing(tmp_path, monkeypatch, payload):
    service, client, item, calls = setup(tmp_path, monkeypatch, payload)
    calls['verdict'] = 'mismatch'
    async def run():
        async with client:
            for index in range(5):
                advance(service)
                result = service.submit(USER, item, 'filmarks', f'1/{index + 2}')
                await service.run_once()
                assert service.get(result['id'])['status'] == 'rejected'
                assert service.quota(USER['id'])['remaining'] == 4 - index
            advance(service)
            with pytest.raises(HTTPException) as caught:
                service.submit(USER, item, 'filmarks', '1/99')
            assert caught.value.status_code == 429 and calls['model'] == 5
            quota = service.quota(USER['id'])
            assert service.quota(USER['id'], datetime.fromisoformat(quota['resets_at']).timestamp() + 1)['remaining'] == 5
    asyncio.run(run())
    assert today(datetime(2026, 9, 28, 16, tzinfo=timezone.utc).timestamp()) == '2026-09-29'


@pytest.mark.parametrize('failure', ['unavailable', 'bad_json', 'low_confidence', 'extra_id'])
def test_failures_and_uncertain_decisions_do_not_charge_or_save(tmp_path, monkeypatch, payload, failure):
    service, client, item, calls = setup(tmp_path, monkeypatch, payload)
    if failure == 'low_confidence':
        calls['confidence'] = 0.5
    else:
        calls[failure] = True
    result = service.submit(USER, item, 'filmarks', '1/2')
    async def run():
        async with client:
            await service.run_once()
    asyncio.run(run())
    record = service.get(result['id'])
    assert record['status'] == ('uncertain' if failure == 'low_confidence' else 'error')
    assert service.quota(USER['id'])['remaining'] == 5
    assert not service.mappings.detail(item)['overrides']
    assert 'private-model-key' not in json.dumps(record)


def test_duplicate_review_is_cached_across_users_and_not_charged_twice(tmp_path, monkeypatch, payload):
    service, client, item, calls = setup(tmp_path, monkeypatch, payload)
    calls['verdict'] = 'mismatch'
    first = service.submit(USER, item, 'filmarks', '1/2')
    assert service.submit(USER, item, 'filmarks', '1/2')['id'] == first['id']
    async def run():
        async with client:
            await service.run_once()
            assert service.submit(USER, item, 'filmarks', '1/2')['id'] == first['id']
            service.submit({'id': 72, 'username': 'second-user'}, item, 'filmarks', '1/2')
            await service.run_once()
    asyncio.run(run())
    assert calls['model'] == 1 and calls['site'] == 1
    assert service.quota(71)['errors'] == 1 and service.quota(72)['errors'] == 1


def test_parallel_submissions_cannot_bypass_pending_limit(tmp_path, monkeypatch, payload):
    service, client, item, calls = setup(tmp_path, monkeypatch, payload)
    def submit(identifier):
        try:
            return service.submit(USER, item, 'filmarks', identifier)['status']
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ['1/2', '1/3']))
    assert results.count('queued') == 1
    assert any(value in {409, 429} for value in results)
    assert service.quota(USER['id'])['pending'] and calls['model'] == 0
    asyncio.run(client.aclose())


def test_concurrent_admin_change_cannot_be_overwritten_or_charge_user(tmp_path, monkeypatch, payload):
    service, client, item, calls = setup(tmp_path, monkeypatch, payload)
    result = service.submit(USER, item, 'filmarks', '1/2')
    job = service._claim()
    service.mappings.save(item, {'filmarks': {'mode': 'disabled'}}, 0, service.repository.snapshot().entries)
    service._complete(job, item, {'verdict': 'match', 'reason': 'match'}, {})
    assert service.get(result['id'])['status'] == 'conflict'
    assert service.mappings.detail(item)['item']['mapping_sources']['filmarks'] == 'disabled'
    assert service.quota(USER['id'])['remaining'] == 5
    asyncio.run(client.aclose())


def test_expired_inflight_review_is_not_automatically_billed_or_recalled(tmp_path, monkeypatch, payload):
    service, client, item, calls = setup(tmp_path, monkeypatch, payload)
    result = service.submit(USER, item, 'filmarks', '1/2')
    service._claim()
    with service.cache.connect() as db:
        db.execute('UPDATE contributions SET lease=0')
    assert service._claim() is None
    assert service.get(result['id'])['status'] == 'error'
    assert calls['model'] == 0 and service.quota(USER['id'])['remaining'] == 5
    asyncio.run(client.aclose())


def test_admin_can_correct_model_rejection_refund_and_keep_credit(tmp_path, monkeypatch, payload):
    service, client, item, calls = setup(tmp_path, monkeypatch, payload)
    calls['verdict'] = 'mismatch'
    result = service.submit(USER, item, 'filmarks', '1/2')
    service.reviewer.model = 'updated-model-before-processing'
    async def run():
        async with client:
            await service.run_once()
            assert service.quota(USER['id'])['remaining'] == 4
            service.approve(result['id'], 'admin-72')
            assert service.quota(USER['id'])['remaining'] == 5
            with service.cache.connect() as db:
                assert db.execute('SELECT COUNT(*) FROM mapping_review_cache').fetchone()[0] == 0
            await service.run_once()
    asyncio.run(run())
    assert service.mappings.detail(item)['item']['mapping_contributors']['filmarks']['bgm_id'] == USER['id']
    assert service.get(result['id'])['score_status'] == 'ok'


def test_wrong_canonical_work_does_not_invoke_model_or_charge(tmp_path, monkeypatch, payload):
    service, client, item, calls = setup(tmp_path, monkeypatch, payload)
    calls['canonical_id'] = '9/9'
    result = service.submit(USER, item, 'filmarks', '1/2')
    async def run():
        async with client:
            await service.run_once()
    asyncio.run(run())
    assert service.get(result['id'])['status'] == 'error'
    assert calls['model'] == 0 and service.quota(USER['id'])['remaining'] == 5
    assert not service.mappings.detail(item)['overrides']


def test_score_outage_keeps_accepted_mapping_credit_and_hourly_tracking(tmp_path, monkeypatch, payload):
    service, client, item, calls = setup(tmp_path, monkeypatch, payload)
    result = service.submit(USER, item, 'filmarks', '1/2')
    async def run():
        async with client:
            await service.run_once()
            calls['site_unavailable'] = True
            await service.run_once()
    asyncio.run(run())
    record = service.get(result['id'])
    assert record['status'] == 'accepted' and record['score_status'] == 'unavailable'
    assert service.mappings.detail(item)['item']['mapping_contributors']['filmarks']['bgm_id'] == USER['id']
    assert item['catalog_id'] in service.analytics.tracked()
    assert calls['model'] == 1 and service.quota(USER['id'])['remaining'] == 5


def test_submission_api_requires_session_csrf_and_does_not_accept_spoofed_author(client):
    item = client.app.state.contributions.repository.snapshot().entries[0]
    body = {'catalog_id': item['catalog_id'], 'provider': 'filmarks', 'id': '1/2'}
    assert client.post('/api/v1/contributions', json=body).status_code == 401
    token = client.app.state.auth.login({'id': 71, 'username': 'verified-user'})
    client.cookies.set(SESSION_COOKIE, token)
    assert client.post('/api/v1/contributions', json=body).status_code == 403
    csrf = client.get('/api/v1/auth/me').json()['csrf_token']
    headers = {'X-CSRF-Token': csrf}
    assert client.post('/api/v1/contributions', json={**body, 'username': 'admin'}, headers=headers).status_code == 422
    assert client.post('/api/v1/contributions', json=body, headers=headers).status_code == 503
    service = client.app.state.contributions
    service.reviewer.enabled = True
    result = service.submit(USER, item, 'filmarks', '1/2')
    assert client.get('/api/v1/contributions/' + result['id']).status_code == 200
    other = client.app.state.auth.login({'id': 72, 'username': 'other'})
    client.cookies.set(SESSION_COOKIE, other)
    assert client.get('/api/v1/contributions/' + result['id']).status_code == 404
