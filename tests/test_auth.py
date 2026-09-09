import time

import pytest
from fastapi.testclient import TestClient
from sabc.app import app
from sabc import auth


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('SABC_ACCESS_PASSWORD','private-test-password-123456')
    monkeypatch.setenv('SABC_UI_ORIGIN','https://work.example')
    auth.sessions.clear(); auth.attempts.clear()
    return TestClient(app,base_url='https://work.example')


def test_private_data_requires_login(client):
    for path in ('/api/bootstrap','/api/settings','/api/projects/missing','/api/local-sources'):
        assert client.get(path).status_code==401
    assert client.post('/api/projects',json={'name':'unauthorized'}).status_code==401
    assert client.get('/api/health').json()=={'status':'ok'}


def test_login_cookie_expiry_logout_and_rotation(client,monkeypatch):
    assert client.post('/api/auth/login',json={'password':'wrong'}).status_code==401
    r=client.post('/api/auth/login',json={'password':'private-test-password-123456'})
    assert r.status_code==200
    cookie=r.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=strict' in cookie
    assert client.get('/api/auth/session').json()['authenticated']
    assert client.get('/api/bootstrap').status_code==200
    old=client.cookies.get(auth.COOKIE)
    assert client.post('/api/auth/logout').status_code==200
    client.cookies.set(auth.COOKIE,old)
    assert client.get('/api/bootstrap').status_code==401
    client.cookies.clear()
    client.post('/api/auth/login',json={'password':'private-test-password-123456'})
    monkeypatch.setenv('SABC_ACCESS_PASSWORD','rotated-test-password-123456')
    assert client.get('/api/bootstrap').status_code==401


def test_cross_origin_login_and_throttling(client):
    assert client.post('/api/auth/login',json={'password':'private-test-password-123456'},headers={'Origin':'https://evil.example'}).status_code==403
    for _ in range(30):
        assert client.post('/api/auth/login',json={'password':'wrong'}).status_code==401
    assert client.post('/api/auth/login',json={'password':'wrong'}).status_code==429


def test_cloud_auth_is_fail_closed(client,monkeypatch):
    monkeypatch.delenv('SABC_ACCESS_PASSWORD')
    monkeypatch.setenv('SABC_REQUIRE_AUTH','1')
    assert client.get('/api/bootstrap').status_code==401
    assert client.post('/api/auth/login',json={'password':'anything'}).status_code==503


def test_expired_session(client):
    client.post('/api/auth/login',json={'password':'private-test-password-123456'})
    for key in auth.sessions: auth.sessions[key]=(time.time()-1,auth.password_hash())
    assert client.get('/api/bootstrap').status_code==401
