"""Official OAuth and read-only catalog surface; no live credentials/network/MIDI."""
import hashlib
import io
import inspect
import json
import os
import time
from urllib.parse import parse_qs, urlsplit
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient

from devices.axefx3 import tone3000 as t3, tone3000_routes
import server


HEADERS = {'X-ToneCommand': '1'}
TONE = {'id': 50174, 'title': '<Metallica Rhythm>', 'description': 'Creator claim, not proof',
        'gear': 'amp-cab', 'format': 'nam', 'license': 'T3K', 'models_count': 1,
        'user': {'username': 'creator', 'avatar_url': 'https://www.tone3000.com/avatar'},
        'images': ['https://www.tone3000.com/image']}
MODEL = {'id': 42, 'tone_id': 50174, 'name': 'MOP nam', 'size': 'standard',
         'architecture_version': 2, 'model_url': 'https://www.tone3000.com/api/v1/models/42/file'}


@pytest.fixture
def client():
    return TestClient(server.app, base_url='http://127.0.0.1:8909', headers=HEADERS)


@pytest.fixture
def logged_in(monkeypatch):
    t3.client.configure('public-client-123')
    t3.client._save_session({'access_token': 'access-secret', 'refresh_token': 'refresh-secret',
                            'expires_at': time.time() + 3600,
                            'user': {'username': 'player', 'display_name': 'Player'}})
    calls = []

    def request(path, **kwargs):
        calls.append((path, kwargs))
        if path == '/user':
            return {'username': 'player'}
        if path.startswith('/tones/search') or path.startswith('/tones/favorited'):
            return {'data': [TONE], 'total_pages': 2}
        if path.startswith('/tones/50174'):
            return TONE
        if path.startswith('/models?'):
            return {'data': [MODEL]}
        if path == '/models/42':
            return MODEL
        if path.startswith('https:'):
            return b'{"version":"0.7.0","architecture":"SlimmableContainer","weights":[]}'
        raise AssertionError(path)

    monkeypatch.setattr(t3, '_request', request)
    return calls


def begin(client, mode='signin'):
    t3.client.configure('public-client-123')
    response = client.post('/api/axefx3/tone3000/auth/start', json={'mode': mode})
    assert response.status_code == 200
    return parse_qs(urlsplit(response.json()['url']).query)


def token_exchange(monkeypatch):
    calls = []

    def fake(path, **kwargs):
        calls.append((path, kwargs))
        if path == '/oauth/token':
            return {'access_token': 'access-secret', 'refresh_token': 'refresh-secret', 'expires_in': 3600}
        if path == '/user':
            return {'username': 'player', 'email': 'private@example.test', 'access_token': 'must-strip'}
        raise AssertionError(path)

    monkeypatch.setattr(t3, '_request', fake)
    return calls


def test_status_without_configuration_or_hardware(client, monkeypatch):
    monkeypatch.setattr(server, 'get_fm9', lambda: pytest.fail('Account UI must not touch MIDI'))
    result = client.get('/api/axefx3/tone3000/status').json()
    assert result['connected'] is False and result['configured'] is False
    assert result['installation_supported'] is False


@pytest.mark.parametrize('key', ['t3k_cs_do-not-store', 'https://evil.test', 'bad key', 'short'])
def test_reject_secret_keys_and_invalid_client_ids(client, key):
    response = client.post('/api/axefx3/tone3000/config', json={'client_id': key})
    assert response.status_code in (400, 422)
    assert not (t3.storage_dir() / 'config.json').exists()


def test_config_does_not_accept_password_fields(client):
    response = client.post('/api/axefx3/tone3000/config', json={'client_id': 'public-client', 'password': 'must-not-echo'})
    assert response.status_code == 422 and 'must-not-echo' not in response.text


@pytest.mark.parametrize('body', [{}, {'client_id': ''}, {'client_id': '   '}])
def test_missing_key_has_actionable_setup_help_not_generic_422(client, body):
    response = client.post('/api/axefx3/tone3000/config', json=body)
    assert response.status_code == 400
    assert 'Publishable Key' in response.json()['error']
    assert 'stap 2' in response.json()['error']
    assert not (t3.storage_dir() / 'config.json').exists()


def test_secret_key_error_does_not_echo_the_secret(client):
    response = client.post('/api/axefx3/tone3000/config', json={'client_id': 't3k_cs_private-do-not-echo'})
    assert response.status_code == 400
    assert 'Secret Key' in response.json()['error']
    assert 'private-do-not-echo' not in response.text


def test_config_disk_error_is_safe_and_actionable(client, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('Sensitive private filesystem details')
    monkeypatch.setattr(t3, '_write_private', fail)
    response = client.post('/api/axefx3/tone3000/config', json={'client_id': 'public-client'})
    assert response.status_code == 500
    assert 'Sensitive private filesystem details' not in response.text
    assert 'opslaan' in response.json()['error']


def test_start_requires_public_key(client):
    result = client.post('/api/axefx3/tone3000/auth/start', json={})
    assert result.status_code == 400
    assert 'client_id' in result.json()['error']


def test_pkce_cookie_and_official_redirect(client):
    params = begin(client, 'select')
    assert params['redirect_uri'] == ['http://127.0.0.1:8909/api/tone3000/callback']
    assert params['prompt'] == ['select_tone'] and params['architecture'] == ['2']
    assert params['code_challenge_method'] == ['S256']
    pending = t3.client.pending[params['state'][0]]
    import base64
    expected = base64.urlsafe_b64encode(hashlib.sha256(pending['verifier'].encode()).digest()).rstrip(b'=').decode()
    assert params['code_challenge'] == [expected]
    assert 'code_verifier' not in params
    assert len(pending['browser']) > 30
    cookie = next(c for c in client.cookies.jar if c.name == tone3000_routes.COOKIE)
    assert cookie._rest['HttpOnly'] is None and cookie._rest['SameSite'] == 'lax'


def test_success_callback_is_bound_and_replay_is_refused(client, monkeypatch):
    calls = token_exchange(monkeypatch)
    params = begin(client)
    query = {'state': params['state'][0], 'code': 'authorization-secret'}
    response = client.get('/api/tone3000/callback', params=query)
    assert response.status_code == 200
    assert 'access-secret' not in response.text and 'authorization-secret' not in response.text
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert 'no-store' in response.headers['cache-control']
    assert calls[0][1]['form']['code_verifier']
    assert client.get('/api/axefx3/tone3000/status').json()['user']['username'] == 'player'
    assert client.get('/api/tone3000/callback', params=query).status_code == 400


@pytest.mark.parametrize('bad', ['wrong-state', 'missing-cookie', 'wrong-cookie', 'expired'])
def test_callback_refuses_unbound_requests(client, monkeypatch, bad):
    calls = token_exchange(monkeypatch)
    params = begin(client)
    state = params['state'][0]
    if bad == 'wrong-state':
        state = 'wrong'
    if bad == 'missing-cookie':
        client.cookies.clear()
    if bad == 'wrong-cookie':
        client.cookies.clear()
        client.cookies.set(tone3000_routes.COOKIE, 'wrong', path='/api/tone3000')
    if bad == 'expired':
        t3.client.pending[state]['expires'] = 0
    assert client.get('/api/tone3000/callback', params={'state': state, 'code': 'secret'}).status_code == 400
    assert calls == []


def test_cancellation_does_not_login_or_expose_upstream_error(client, monkeypatch):
    calls = token_exchange(monkeypatch)
    params = begin(client)
    result = client.get('/api/tone3000/callback', params={'state': params['state'][0], 'error': '<script>token-secret</script>'})
    assert result.status_code == 400 and calls == []
    assert 'token-secret' not in result.text


@pytest.mark.parametrize('path,body', [('/config', {'client_id': 'public-client'}), ('/disconnect', {}), ('/auth/start', {})])
def test_cross_site_mutations_refused(client, path, body):
    result = client.post('/api/axefx3/tone3000' + path, json=body, headers={'Origin': 'https://evil.test'})
    assert result.status_code == 403


def test_dns_rebinding_and_missing_custom_header_refused():
    evil = TestClient(server.app, base_url='http://evil.test', headers=HEADERS)
    assert evil.get('/api/axefx3/tone3000/status').status_code == 403
    local = TestClient(server.app, base_url='http://127.0.0.1:8909')
    assert local.get('/api/axefx3/tone3000/status').status_code == 403


def test_tokens_never_reach_status_or_planner(client, logged_in):
    t3.client.select_tone(50174, 42)
    result = client.get('/api/axefx3/tone3000/status')
    context = t3.client.planner_context()
    for secret in ('access-secret', 'refresh-secret', 'model_url', 'expires_at'):
        assert secret not in result.text and secret not in context
    assert 'NOT installed' in context and 'amp-cab' in context and 'MOP nam' in context
    assert t3.client.status()['selected']['installed'] is False


def test_token_file_protection(logged_in):
    path = t3.storage_dir() / 'account.dat'
    if os.name == 'nt':
        assert path.read_bytes().startswith(b'DPAPI1\n')
        assert b'access-secret' not in path.read_bytes()
    else:
        assert path.stat().st_mode & 0o777 == 0o600
    assert t3.client._session()['access_token'] == 'access-secret'


def test_storage_cannot_be_put_in_checkout(monkeypatch):
    monkeypatch.setenv('TONECOMMAND_TONE3000_DIR', str(server.ROOT / 'backups' / 'tokens'))
    with pytest.raises(t3.ToneError, match='outside'):
        t3.storage_dir()


def test_search_cache_and_private_collection(client, logged_in):
    for _ in range(2):
        response = client.get('/api/axefx3/tone3000/tones', params={'query': 'Metallica'})
        assert response.status_code == 200
        assert response.json()['data'][0]['creator']['username'] == 'creator'
        assert 'model_url' not in response.text
    assert sum(path.startswith('/tones/search') for path, _ in logged_in) == 1
    assert client.get('/api/axefx3/tone3000/tones', params={'collection': 'favorited'}).status_code == 200


def test_unauthenticated_catalog_is_refused(client):
    assert client.get('/api/axefx3/tone3000/tones').status_code == 401


@pytest.mark.parametrize('params', [{'collection': 'arbitrary'}, {'page': 0}, {'architecture': 'anything'}])
def test_catalog_filter_validation(client, logged_in, params):
    assert client.get('/api/axefx3/tone3000/tones', params=params).status_code == 400


def test_invalid_model_cannot_be_selected(client, logged_in):
    assert client.post('/api/axefx3/tone3000/select', json={'tone_id': 50174, 'model_id': 99}).status_code == 400
    assert t3.client.status()['selected'] is None


def test_download_returns_nam_not_install(client, logged_in, monkeypatch):
    monkeypatch.setattr(server, 'get_fm9', lambda: pytest.fail('Download cannot touch MIDI'))
    response = client.get('/api/axefx3/tone3000/download/42')
    assert response.status_code == 200
    assert response.headers['content-disposition'].endswith('42-MOP-nam.nam"')
    assert json.loads(response.content)['architecture'] == 'SlimmableContainer'
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('url', ['http://www.tone3000.com/file', 'https://evil.test/file',
                                'https://www.tone3000.com.evil.test/file', 'https://user@www.tone3000.com/file',
                                'https://www.tone3000.com:8443/file'])
def test_model_urls_cannot_exfiltrate_bearer_tokens(url):
    with pytest.raises(t3.ToneError):
        t3._official_url(url)


def test_redirect_transport_is_blocked():
    assert t3.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.test') is None


def test_official_model_redirect_strips_credentials_and_downloads_once(monkeypatch):
    seen = []
    destination = 'https://api.tone3000.com/storage/v1/object/public/models/test_a2.nam'
    payload = b'{"version":"0.7.0","architecture":"SlimmableContainer","weights":[]}'

    class Opener:
        def open(self, request, timeout):
            seen.append(request)
            assert timeout == 20
            if len(seen) == 1:
                raise HTTPError(request.full_url, 302, '', {'Location': destination}, io.BytesIO())
            return io.BytesIO(payload)

    monkeypatch.setattr(t3, 'build_opener', lambda *args: Opener())
    result = t3._request('/models/42/download/test_a2.nam', token='secret-token', binary=True)
    assert result == payload and len(seen) == 2
    assert seen[0].get_header('Authorization') == 'Bearer secret-token'
    assert seen[1].full_url == destination
    assert seen[1].get_header('Authorization') is None
    assert seen[1].get_header('Cookie') is None and seen[1].data is None


@pytest.mark.parametrize('destination', [
    'https://evil.test/model.nam', 'http://api.tone3000.com/storage/v1/object/public/models/test.nam',
    'https://api.tone3000.com.evil.test/storage/v1/object/public/models/test.nam',
    'https://user@api.tone3000.com/storage/v1/object/public/models/test.nam',
    'https://api.tone3000.com:8443/storage/v1/object/public/models/test.nam',
    'https://api.tone3000.com/storage/v1/object/public/avatars/test.nam',
    'https://api.tone3000.com/storage/v1/object/public/models/../private/test.nam',
    'https://api.tone3000.com/storage/v1/object/public/models/test.nam?token=secret',
    'https://api.tone3000.com/storage/v1/object/public/models/test.nam#fragment',
])
def test_download_rejects_unexpected_redirects_without_second_request(monkeypatch, destination):
    seen = []

    class Opener:
        def open(self, request, timeout):
            seen.append(request)
            raise HTTPError(request.full_url, 302, '', {'Location': destination}, io.BytesIO())

    monkeypatch.setattr(t3, 'build_opener', lambda *args: Opener())
    with pytest.raises(t3.ToneError):
        t3._request('/models/42/download/test_a2.nam', token='secret-token', binary=True)
    assert len(seen) == 1


def test_second_redirect_is_not_followed(monkeypatch):
    seen = []
    destination = 'https://api.tone3000.com/storage/v1/object/public/models/test_a2.nam'

    class Opener:
        def open(self, request, timeout):
            seen.append(request)
            raise HTTPError(request.full_url, 302, '', {'Location': destination}, io.BytesIO())

    monkeypatch.setattr(t3, 'build_opener', lambda *args: Opener())
    with pytest.raises(t3.ToneError):
        t3._request('/models/42/download/test_a2.nam', token='secret-token', binary=True)
    assert len(seen) == 2
    assert seen[1].get_header('Authorization') is None


def test_api_json_redirect_is_never_followed(monkeypatch):
    seen = []

    class Opener:
        def open(self, request, timeout):
            seen.append(request)
            raise HTTPError(request.full_url, 302, '', {'Location':
                'https://api.tone3000.com/storage/v1/object/public/models/test.nam'}, io.BytesIO())

    monkeypatch.setattr(t3, 'build_opener', lambda *args: Opener())
    with pytest.raises(t3.ToneError):
        t3._request('/user', token='secret-token')
    assert len(seen) == 1


def test_redirected_model_still_obeys_download_size_limit(monkeypatch):
    seen = []
    monkeypatch.setattr(t3, 'MAX_MODEL_BYTES', 16)

    class Opener:
        def open(self, request, timeout):
            seen.append(request)
            if len(seen) == 1:
                raise HTTPError(request.full_url, 302, '', {'Location':
                    'https://api.tone3000.com/storage/v1/object/public/models/test.nam'}, io.BytesIO())
            return io.BytesIO(b'x' * 17)

    monkeypatch.setattr(t3, 'build_opener', lambda *args: Opener())
    with pytest.raises(t3.ToneError, match='size limit'):
        t3._request('/models/42/download/test.nam', token='secret-token', binary=True)
    assert len(seen) == 2 and seen[1].get_header('Authorization') is None


def test_download_html_is_not_accepted(client, logged_in, monkeypatch):
    previous = t3._request

    def bad(path, **kwargs):
        return b'<html>Not a model</html>' if kwargs.get('binary') else previous(path, **kwargs)

    monkeypatch.setattr(t3, '_request', bad)
    assert client.get('/api/axefx3/tone3000/download/42').status_code == 502


def test_disconnect_clears_tokens_candidates_and_cache(client, logged_in):
    t3.client.select_tone(50174, 42)
    t3.client.search('Metallica')
    assert client.post('/api/axefx3/tone3000/disconnect', json={}).status_code == 200
    assert t3.client.status()['connected'] is False
    assert t3.client.status()['selected'] is None
    assert t3.client.search_cache == {} and not (t3.storage_dir() / 'account.dat').exists()
    assert t3.client.config()['client_id'] == 'public-client-123'


def test_refresh_rotates_credentials_without_public_exposure(client, logged_in, monkeypatch):
    session = t3.client._session()
    session['expires_at'] = 0
    t3.client._save_session(session)
    seen = []

    def refresh(path, **kwargs):
        seen.append(kwargs)
        return {'access_token': 'rotated-access', 'refresh_token': 'rotated-refresh', 'expires_in': 3600}

    monkeypatch.setattr(t3, '_request', refresh)
    assert t3.client._access() == 'rotated-access'
    assert seen[0]['form']['refresh_token'] == 'refresh-secret'
    assert 'rotated' not in client.get('/api/axefx3/tone3000/status').text


def test_expired_refresh_forces_reconnect(client, logged_in, monkeypatch):
    session = t3.client._session()
    session['expires_at'] = 0
    t3.client._save_session(session)

    def failed(*args, **kwargs):
        raise t3.ToneError('invalid grant', 400)

    monkeypatch.setattr(t3, '_request', failed)
    assert client.get('/api/axefx3/tone3000/tones').status_code == 401
    assert t3.client.status()['connected'] is False
