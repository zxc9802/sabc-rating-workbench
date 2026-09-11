import hashlib
import time
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient
import sabc.app as module
from sabc import sso
from sabc.jobs import Jobs
from sabc.tenancy import AccountStore, account_id


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv('SABC_AUTH_MODE', 'sso')
    monkeypatch.setenv('SABC_SSO_MAIN_ORIGIN', 'https://main.example')
    monkeypatch.setenv('SABC_UI_ORIGIN', 'https://work.example')
    monkeypatch.setenv('SABC_SSO_CLIENT_SECRET', 'x' * 40)
    monkeypatch.setenv('SABC_DB', str(tmp_path / 'legacy.db'))
    store = AccountStore(tmp_path / 'legacy.db')
    store.legacy.save('projects', {'id': 'legacy', 'name': 'old'})
    monkeypatch.setattr(module, 'store', store)
    yield store


def client_for(user):
    client = TestClient(module.app, base_url='https://work.example')
    token = 'test-session-' + user
    sso.SessionStore().save(hashlib.sha256(token.encode()).hexdigest(), {
        'user': {'id': user}, 'token': 'main-token', 'expires': time.time() + 3600, 'checked': time.time()})
    client.cookies.set(sso.COOKIE, token)
    return client


def test_no_password_bypass_and_no_legacy_access(setup):
    client = TestClient(module.app, base_url='https://work.example')
    assert client.get('/api/bootstrap').status_code == 401
    assert client.post('/api/auth/login', json={'password': 'anything'}).status_code == 404
    assert client.get('/api/auth/session').json()['mode'] == 'sso'
    assert client_for('a').get('/api/bootstrap').json()['projects'] == []
    with pytest.raises(PermissionError):
        setup.list('projects')


def test_account_data_and_foreign_ids(setup):
    a, b = client_for('a'), client_for('b')
    a.put('/api/company', json={'name': 'Company A'})
    p = a.post('/api/projects', json={'name': 'A project'}).json()['id']
    assert b.get('/api/bootstrap').json()['company'] == {}
    assert b.get('/api/bootstrap').json()['projects'] == []
    assert b.get('/api/projects/' + p).status_code == 404
    b.post('/api/projects/delete', json={'ids': [p]})
    assert a.get('/api/projects/' + p).status_code == 200
    assert a.get('/api/bootstrap').json()['company']['name'] == 'Company A'
    assert a.put('/api/settings', json={}).status_code == 403
    for user in ('a', 'b'):
        context = account_id.set(user)
        try:
            setup.save('evidence', {'id': 'same', 'project_id': p, 'title': user})
            setup.save('assessments', {'id': 'same', 'project_id': p, 'rating': user})
            assert setup.get('evidence', 'same')['title'] == user
        finally:
            account_id.reset(context)
    assert setup.accounts[hashlib.sha256(b'a').hexdigest()].path != setup.accounts[hashlib.sha256(b'b').hexdigest()].path


def test_callback_state_and_exchange_protocol(setup, monkeypatch):
    c = TestClient(module.app, base_url='https://work.example', follow_redirects=False)
    assert c.get('/api/sso/callback?ticket=x&state=' + 'x'*32).status_code == 400
    start = c.get('/api/sso/start')
    assert start.status_code == 302 and 'externalSso=sabcxm' in start.headers['location']
    state = c.cookies.get(sso.STATE_COOKIE)
    calls = []
    def exchange(url, **kw):
        calls.append(kw)
        return httpx.Response(200, json={'data': {'user': {'id': 'a'}, 'token': 'main-token', 'expiresAt': (time.time()+3*86400)*1000}}, request=httpx.Request('POST', url))
    def verify(url, **kw):
        return httpx.Response(200, json={'data': {'user': {'id': 'a'}}}, request=httpx.Request('GET', url))
    monkeypatch.setattr(sso.httpx, 'post', exchange)
    monkeypatch.setattr(sso.httpx, 'get', verify)
    assert c.get('/api/sso/callback?ticket=x&state='+'z'*32).status_code == 400
    assert not calls
    response = c.get('/api/sso/callback', params={'ticket': 'single-use', 'state': state})
    assert response.status_code == 303
    key = hashlib.sha256(c.cookies.get(sso.COOKIE).encode()).hexdigest()
    assert sso.SessionStore().get(key)['expires'] > time.time() + 2 * 86400
    assert 'Max-Age=259' in response.headers['set-cookie']
    assert calls[0]['headers']['x-qycm-sso-client-secret'] == 'x'*40
    assert 'HttpOnly' in response.headers['set-cookie'] and 'Secure' in response.headers['set-cookie']
    assert c.get('/api/bootstrap').status_code == 200
    assert c.get('/api/sso/callback', params={'ticket': 'single-use', 'state': state}).status_code == 400
    assert c.post('/api/auth/logout').status_code == 200
    assert c.get('/api/bootstrap').status_code == 401


@pytest.mark.parametrize('status,expected', [(401,401), (403,401), (503,503)])
def test_revocation_and_fail_closed(setup, monkeypatch, status, expected):
    c = client_for('a')
    sessions = sso.SessionStore()
    key = hashlib.sha256(c.cookies.get(sso.COOKIE).encode()).hexdigest()
    entry = sessions.get(key)
    entry['checked'] = 0
    sessions.save(key, entry)
    monkeypatch.setattr(sso.httpx, 'get', lambda url, **kw: httpx.Response(status, request=httpx.Request('GET', url)))
    assert c.get('/api/bootstrap').status_code == expected


def test_background_context_and_cancel_are_account_scoped(setup):
    manager = Jobs()
    release = Event()
    started = {u: Event() for u in ('a', 'b')}
    def action():
        user = account_id.get()
        started[user].set()
        assert release.wait(3)
        setup.save('evidence', {'id': 'background', 'title': user})
        return user
    try:
        for user in ('a', 'b'):
            context = account_id.set(user)
            try: manager.submit(setup, 'same-job', 'same-project', {}, action)
            finally: account_id.reset(context)
        assert all(event.wait(1) for event in started.values())
        context = account_id.set('a')
        try: manager.cancel(setup, 'same-job')
        finally: account_id.reset(context)
        release.set()
        manager.pool.shutdown()
        for user in ('a','b'):
            context = account_id.set(user)
            try:
                assert setup.get('evidence','background')['title'] == user
                assert setup.get('jobs','same-job')['status'] == ('cancelled' if user == 'a' else 'success')
            finally: account_id.reset(context)
    finally:
        release.set()
        manager.pool.shutdown()


def test_session_survives_new_process_without_plaintext_credentials(setup):
    import os
    import subprocess
    import sys
    c = client_for('restart-user')
    key = hashlib.sha256(c.cookies.get(sso.COOKIE).encode()).hexdigest()
    sessions = sso.SessionStore()
    raw = sessions.path.read_bytes()
    assert b'main-token' not in raw and b'restart-user' not in raw
    assert sessions.path.stat().st_mode & 0o777 == 0o600
    script = """
import sys
from fastapi.testclient import TestClient
from sabc.app import app
from sabc.sso import COOKIE
with TestClient(app, base_url='https://work.example') as client:
    client.cookies.set(COOKIE, sys.argv[1])
    assert client.get('/api/auth/session').json()['user']['id'] == 'restart-user'
    assert client.get('/api/bootstrap').status_code == 200
"""
    subprocess.run([sys.executable, '-c', script, c.cookies.get(sso.COOKIE)], check=True, env=os.environ.copy())
    assert c.get('/api/bootstrap').status_code == 200


def test_transient_failure_recovers_but_revocation_is_persistent(setup, monkeypatch):
    c = client_for('a')
    sessions = sso.SessionStore()
    key = hashlib.sha256(c.cookies.get(sso.COOKIE).encode()).hexdigest()
    entry = sessions.get(key)
    entry['checked'] = 0
    sessions.save(key, entry)
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout('temporarily unavailable')
    monkeypatch.setattr(sso.httpx, 'get', timeout)
    assert c.get('/api/bootstrap').status_code == 503
    assert sso.SessionStore().get(key) is not None
    monkeypatch.setattr(sso.httpx, 'get', lambda url, **kw: httpx.Response(200, json={'data': {'user': {'id': 'a'}}}, request=httpx.Request('GET', url)))
    assert c.get('/api/bootstrap').status_code == 200
    sessions.save(key, entry)
    monkeypatch.setattr(sso.httpx, 'get', lambda url, **kw: httpx.Response(401, request=httpx.Request('GET', url)))
    assert c.get('/api/bootstrap').status_code == 401
    assert sso.SessionStore().get(key) is None
    assert not sessions.refresh(key, entry)
    assert sso.SessionStore().get(key) is None


def test_expiry_secret_rotation_and_logout_remain_effective(setup, monkeypatch):
    c = client_for('a')
    sessions = sso.SessionStore()
    key = hashlib.sha256(c.cookies.get(sso.COOKIE).encode()).hexdigest()
    entry = sessions.get(key)
    assert c.post('/api/auth/logout').status_code == 200
    assert sso.SessionStore().get(key) is None
    assert not sessions.refresh(key, entry)
    c.cookies.set(sso.COOKIE, 'test-session-a')
    assert c.get('/api/bootstrap').status_code == 401
    sessions.save(key, {**entry, 'expires': time.time() - 1})
    assert c.get('/api/bootstrap').status_code == 401
    sessions.save(key, entry)
    monkeypatch.setenv('SABC_SSO_CLIENT_SECRET', 'rotated-secret' * 4)
    assert c.get('/api/bootstrap').status_code == 401
