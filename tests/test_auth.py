import asyncio
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from services.auth import AuthStore, Profile, SESSION_COOKIE, STATE_COOKIE, digest, initial_admin, oauth_config
from services.ratings import RatingCache


def configure(monkeypatch):
    monkeypatch.setenv('BGM_CLIENT_ID', 'test-app')
    monkeypatch.setenv('BGM_CLIENT_SECRET', 'test-secret')
    monkeypatch.setenv('BGM_REDIRECT_URI', 'http://127.0.0.1:5002/api/v1/auth/bangumi/callback')


def session(client, uid=71):
    token = client.app.state.auth.login({'id': uid, 'username': f'user{uid}', 'nickname': 'Test User'})
    client.cookies.set(SESSION_COOKIE, token)
    return client.app.state.auth.session(token)


def test_oauth_state_is_browser_bound_single_use_and_expiring(tmp_path):
    auth = AuthStore(RatingCache(tmp_path / 'auth.db'))
    state, browser = auth.begin('//evil.example')
    with pytest.raises(ValueError):
        auth.consume(state, 'wrong-browser')
    assert auth.consume(state, browser) == '/'
    with pytest.raises(ValueError):
        auth.consume(state, browser)
    state, browser = auth.begin('/admin')
    with auth.cache.connect() as db:
        db.execute('UPDATE oauth_states SET expires_at=0')
    with pytest.raises(ValueError):
        auth.consume(state, browser)


def test_oauth_login_verifies_identity_rotates_session_and_never_exposes_token(client, monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv('BGM_ADMIN_IDS', '71')
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path == '/oauth/access_token':
            assert b'client_secret=test-secret' in request.content
            return httpx.Response(200, json={'access_token': 'private-bgm-token', 'user_id': 71, 'expires_in': 604800})
        assert str(request.url) == 'https://api.bgm.tv/v0/me'
        assert request.headers['Authorization'] == 'Bearer private-bgm-token'
        return httpx.Response(200, json={'id': 71, 'username': 'verified-user', 'nickname': 'Nickname'})
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client.app.state.ratings.client = upstream
    previous = client.app.state.auth.login({'id': 71, 'username': 'old-name'})
    client.cookies.set(SESSION_COOKIE, previous)
    login = client.get('/api/v1/auth/bangumi/login?return_to=/admin', follow_redirects=False)
    assert login.status_code == 302
    parameters = parse_qs(urlparse(login.headers['location']).query)
    assert parameters['redirect_uri'] == ['http://127.0.0.1:5002/api/v1/auth/bangumi/callback']
    assert 'HttpOnly' in login.headers['set-cookie'] and 'SameSite=lax' in login.headers['set-cookie']
    state = parameters['state'][0]
    assert client.get(f'/api/v1/auth/bangumi/callback?state=bad&code=code', follow_redirects=False).status_code == 400
    response = client.get(f'/api/v1/auth/bangumi/callback?state={state}&code=code', follow_redirects=False)
    assert response.status_code == 303 and response.headers['location'] == '/admin'
    assert 'private-bgm-token' not in str(response.headers)
    assert client.app.state.auth.session(previous) is None
    client.cookies.delete(SESSION_COOKIE, domain='', path='/')
    me = client.get('/api/v1/auth/me')
    assert me.json()['user']['username'] == 'verified-user' and me.json()['user']['role'] == 'admin'
    assert me.headers['cache-control'] == 'no-store'
    assert 'private-bgm-token' not in me.text
    assert client.get(f'/api/v1/auth/bangumi/callback?state={state}&code=code', follow_redirects=False).status_code == 400
    assert len(calls) == 2
    with client.app.state.auth.cache.connect() as db:
        raw = db.execute('SELECT token_hash FROM sessions').fetchone()[0]
        assert raw == digest(client.cookies.get(SESSION_COOKIE))
    asyncio.run(upstream.aclose())


def test_identity_mismatch_and_remote_plaintext_oauth_are_rejected(client, monkeypatch):
    configure(monkeypatch)
    def handler(request):
        return httpx.Response(200, json={'access_token': 'secret', 'user_id': 1, 'expires_in': 999}) if request.method == 'POST' else httpx.Response(200, json={'id': 2, 'username': 'wrong-user'})
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client.app.state.ratings.client = upstream
    response = client.get('/api/v1/auth/bangumi/login', follow_redirects=False)
    state = parse_qs(urlparse(response.headers['location']).query)['state'][0]
    response = client.get(f'/api/v1/auth/bangumi/callback?state={state}&code=test', follow_redirects=False)
    assert response.headers['location'] == '/?auth_error=unavailable'
    assert client.get('/api/v1/auth/me').json()['user'] is None
    monkeypatch.setenv('BGM_REDIRECT_URI', 'http://public.example/api/v1/auth/bangumi/callback')
    assert not oauth_config()['enabled']
    assert client.get('/api/v1/auth/bangumi/login', follow_redirects=False).status_code == 503
    asyncio.run(upstream.aclose())


def test_user_cannot_use_admin_routes_and_cookie_writes_require_csrf(client, monkeypatch):
    configure(monkeypatch)
    user = session(client)
    assert client.get('/api/v1/admin/users').status_code == 403
    assert client.put('/api/v1/admin/users/71/role', json={'role': 'admin'}, headers={'X-CSRF-Token': user['csrf']}).status_code == 403
    assert client.post('/api/v1/auth/logout').status_code == 403
    assert client.post('/api/v1/auth/logout', headers={'X-CSRF-Token': user['csrf'], 'Origin': 'https://evil.example'}).status_code == 403
    assert client.get('/api/v1/auth/me').json()['user']['id'] == 71
    assert client.post('/api/v1/auth/logout', headers={'X-CSRF-Token': user['csrf']}).status_code == 200
    assert client.get('/api/v1/auth/me').json()['user'] is None


def test_roles_persist_last_admin_is_protected_and_changes_apply_to_existing_sessions(client, monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv('BGM_ADMIN_IDS', '71')
    admin = session(client)
    second_token = client.app.state.auth.login({'id': 72, 'username': 'second-user', 'role': 'admin'})
    assert client.app.state.auth.session(second_token)['role'] == 'user'
    headers = {'X-CSRF-Token': admin['csrf']}
    assert client.put('/api/v1/admin/users/71/role', json={'role': 'user'}, headers=headers).status_code == 409
    assert client.put('/api/v1/admin/users/72/role', json={'role': 'admin'}, headers=headers).status_code == 200
    assert client.app.state.auth.session(second_token)['role'] == 'admin'
    assert client.put('/api/v1/admin/users/71/role', json={'role': 'user'}, headers=headers).status_code == 200
    assert client.get('/api/v1/admin/users').status_code == 403
    token = client.app.state.auth.login({'id': 71, 'username': 'renamed-user'})
    assert client.app.state.auth.session(token)['role'] == 'user'


@pytest.mark.parametrize('configured', ['71', 'custom_user', ' https://bgm.tv/user/custom_user ',
                                      'https://bangumi.tv/user/71/', 'https://chii.in/user/custom_user',
                                      '72, custom_user'])
def test_admin_bootstrap_accepts_uid_username_or_profile_url(tmp_path, monkeypatch, configured):
    monkeypatch.setenv('BGM_ADMIN_IDS', configured)
    auth = AuthStore(RatingCache(tmp_path / 'auth.db'))
    token = auth.login({'id': 71, 'username': 'custom_user'})
    assert auth.session(token)['role'] == 'admin'
    other = auth.login({'id': 73, 'username': 'other', 'nickname': 'custom_user'})
    assert auth.session(other)['role'] == 'user'
    with auth.cache.connect() as db:
        db.execute("UPDATE users SET role='user' WHERE id=71")
    assert auth.session(auth.login({'id': 71, 'username': 'custom_user'}))['role'] == 'user'


@pytest.mark.parametrize('configured', ['72', 'https://evil.example/user/custom_user',
                                      'https://bgm.tv/subject/custom_user', 'https://bgm.tv/user/custom_user/extra',
                                      'https://bgm.tv/user/custom_user?admin=1', 'https://bgm.tv/user/custom_user#admin',
                                      'https://bgm.tv@evil.example/user/custom_user', 'https://bgm.tv:bad/user/custom_user',
                                      'https://bgm.tv.evil.example/user/custom_user', 'https://[bad/user/custom_user'])
def test_admin_bootstrap_rejects_unrelated_ids_and_invalid_profile_urls(monkeypatch, configured):
    monkeypatch.setenv('BGM_ADMIN_IDS', configured)
    assert not initial_admin(Profile(id=71, username='custom_user'))


def test_numeric_admin_config_only_matches_numeric_uid(monkeypatch):
    monkeypatch.setenv('BGM_ADMIN_IDS', '72')
    assert not initial_admin(Profile(id=71, username='72'))
