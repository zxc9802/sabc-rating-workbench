"""Regression checks from the September security and behavior reviews."""
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from starlette.exceptions import HTTPException
from fastapi.testclient import TestClient

import sabc.app as module
from sabc import checkpoints, model_router, report_qa, attachments, auth
from sabc.jobs import Jobs
from tests.test_app import client
from tests.test_sso import setup, client_for


def test_full_history_does_not_link_old_budget_to_new_question():
    history = [{'role': 'user', 'content': '预算大概5万'},
               {'role': 'assistant', 'content': '整个项目的总投入上限是多少？'}]
    result = {'reply': 'test', 'questions': [], 'dimension_coverage': {'cash': {'items': {
        'investment_limit': {'status': 'known', 'source': 'user', 'quote': '5万'}}}}}
    checkpoints.normalize(result, {'messages': history}, {}, [],
                          history + [{'role': 'user', 'content': '这个我们还没定'}])
    assert not result['dimension_coverage']['cash']['items']['investment_limit']['verified']


def test_deepseek_only_skips_empty_route(monkeypatch):
    for key in ('SABC_MIXTOKEN_API_KEY', 'SABC_FAL_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('SABC_DEEPSEEK_API_KEY', 'synthetic')
    calls = []
    assert model_router.routed('analysis', {'model': '', 'base_url': '', 'key': ''},
                               lambda r: calls.append(r) or 'ok') == 'ok'
    assert len(calls) == 1 and calls[0]['deepseek']
    monkeypatch.setattr(report_qa, 'routed', lambda *_: '通过备用连接回答')
    assert report_qa.answer({'base_url': '', 'model': ''}, '',
                           {'snapshot': {}, 'result': {}}, [], '解释报告') == '通过备用连接回答'


@pytest.mark.parametrize('value', ['中文错误类型', '', [], {}])
def test_project_type_rejected_at_write_boundary(client, value):
    assert client.post('/api/projects', json={'name': 'test', 'project_type': value}).status_code == 422
    pid = client.post('/api/projects', json={'name': 'test'}).json()['id']
    assert client.patch('/api/projects/' + pid, json={'project_type': value}).status_code == 422
    assert client.get('/api/projects/' + pid).json()['project']['project_type'] is None


def test_bad_date_has_actionable_message(client):
    pid = client.post('/api/projects', json={'name': 'test'}).json()['id']
    response = client.post('/api/projects/' + pid + '/lifecycle', json={
        'action': 'set_stage', 'version': 1, 'payload': {'stage': 'during', 'actual_start': ''}})
    assert response.status_code == 422
    assert '日期' in response.json()['detail'] and 'isoformat' not in response.text


def test_health_has_one_public_route(client):
    assert len([r for r in module.app.routes if getattr(r, 'path', '') == '/api/health']) == 1
    assert client.get('/api/health').json() == {'status': 'ok'}


def test_changed_target_does_not_inherit_environment_key(client, monkeypatch):
    monkeypatch.setenv('SABC_MODEL_BASE_URL', 'https://original.example/v1')
    monkeypatch.setenv('SABC_API_KEY', 'synthetic')
    response = client.put('/api/settings', json={'base_url': 'https://other.example/v1', 'model': 'test'})
    assert response.status_code == 422
    response = client.put('/api/settings', json={
        'base_url': 'http://127.0.0.1:1234/v1', 'model': 'local', 'clear_key': True})
    assert response.status_code == 200 and not response.json()['has_key']


def test_cancelled_attachment_cannot_commit_evidence(client, monkeypatch):
    manager = Jobs()
    monkeypatch.setattr(module, 'jobs', manager)
    entered, release = Event(), Event()
    def extract(*_):
        entered.set()
        assert release.wait(3)
        return {'content': 'late result'}
    monkeypatch.setattr(attachments, 'extract', extract)
    pid = client.post('/api/projects', json={'name': 'test'}).json()['id']
    try:
        response = client.post(f'/api/projects/{pid}/attachments', files={'file': ('x.txt', b'hello')})
        ident = response.json()['id']
        assert entered.wait(1)
        assert client.post('/api/jobs/' + ident + '/cancel').json()['status'] == 'cancelled'
    finally:
        release.set()
        manager.pool.shutdown()
    assert not client.get('/api/projects/' + pid).json()['evidence']


def test_oversized_body_rejected_before_multipart_storage(client, monkeypatch):
    import starlette.formparsers as parser
    def unexpected(*_, **__):
        raise AssertionError('multipart storage must not start')
    monkeypatch.setattr(parser, 'SpooledTemporaryFile', unexpected)
    response = client.post('/api/company/import', content=b'x' * 21_000_000,
                           headers={'Content-Type': 'multipart/form-data; boundary=test'})
    assert response.status_code == 413


def test_failed_logins_do_not_lock_other_source(monkeypatch):
    monkeypatch.delenv('SABC_AUTH_MODE', raising=False)
    monkeypatch.setenv('SABC_ACCESS_PASSWORD', 'synthetic-owner-password-12345')
    auth.attempts.clear()
    attacker = TestClient(module.app, client=('192.0.2.1', 1000))
    owner = TestClient(module.app, client=('192.0.2.2', 1001))
    for _ in range(30):
        assert attacker.post('/api/auth/login', json={'password': 'wrong'}).status_code == 401
    assert attacker.post('/api/auth/login', json={'password': 'wrong'}).status_code == 429
    assert owner.post('/api/auth/login', json={'password': 'synthetic-owner-password-12345'}).status_code == 200


def test_sso_configuration_and_audit_do_not_expose_provider(setup, monkeypatch):
    from sabc.tenancy import account_id
    monkeypatch.setenv('SABC_MODEL_BASE_URL', 'https://private-model.example/v1')
    monkeypatch.setenv('SABC_MODEL', 'private-model-name')
    monkeypatch.setenv('SABC_API_KEY', 'synthetic-private-key')
    c = client_for('a')
    response = c.get('/api/bootstrap')
    assert response.status_code == 200 and response.json()['settings']['configured']
    for secret in ('private-model.example', 'private-model-name', 'synthetic-private-key'):
        assert secret not in response.text
    pid = c.post('/api/projects', json={'name': 'a'}).json()['id']
    token = account_id.set('a')
    try:
        setup.save('model_runs', {'project_id': pid, 'provider': 'private-model.example', 'model': 'private-model-name', 'status': 'success'})
    finally:
        account_id.reset(token)
    response = c.get(f'/api/projects/{pid}/model-runs')
    assert response.status_code == 200 and 'private-model' not in response.text
    assert client_for('b').get(f'/api/projects/{pid}/model-runs').status_code == 404


def test_direct_chat_shares_capacity_and_project_guard(client, monkeypatch):
    manager = Jobs()
    monkeypatch.setattr(module, 'jobs', manager)
    entered = [Event(), Event()]
    release = Event()
    pids = [client.post('/api/projects', json={'name': str(i)}).json()['id'] for i in range(3)]
    def hold(pid, *_):
        entered[pids.index(pid)].set()
        assert release.wait(3)
        return {'reply': 'ok'}
    monkeypatch.setattr(module, 'chat_turn', hold)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(client.post, f'/api/projects/{pids[0]}/chat', json={'message': 'x'})
            assert entered[0].wait(1)
            assert client.post(f'/api/projects/{pids[0]}/chat', json={'message': 'y'}).status_code == 409
            second = pool.submit(client.post, f'/api/projects/{pids[1]}/chat', json={'message': 'x'})
            try:
                assert entered[1].wait(1)
                assert client.post(f'/api/projects/{pids[2]}/chat', json={'message': 'x'}).status_code == 429
                assert client.post(f'/api/projects/{pids[2]}/sources/github', json={'query': 'a/b'}).status_code == 429
            finally:
                release.set()
            assert first.result().status_code == second.result().status_code == 200
    finally:
        release.set()
        manager.pool.shutdown()
    assert not manager.active and not manager.projects


def test_sso_queue_bounded_without_blocking_other_account(setup, monkeypatch):
    manager = Jobs()
    monkeypatch.setattr(module, 'jobs', manager)
    release = Event()
    monkeypatch.setattr(module, 'chat', lambda *_: release.wait(3))
    a, b = client_for('a'), client_for('b')
    try:
        for _ in range(4):
            pid = a.post('/api/projects', json={'name': 'a'}).json()['id']
            assert a.post(f'/api/projects/{pid}/start-interview').status_code == 200
        pid = a.post('/api/projects', json={'name': 'extra'}).json()['id']
        assert a.post(f'/api/projects/{pid}/start-interview').status_code == 429
        pid = b.post('/api/projects', json={'name': 'b'}).json()['id']
        response = b.post(f'/api/projects/{pid}/jobs', json={
            'id': str(uuid4()), 'operation': 'chat', 'payload': {'message': 'b'}})
        assert response.status_code == 202
        # Replaying an accepted ID does not consume another queue slot.
        assert b.post(f'/api/projects/{pid}/jobs', json={
            'id': response.json()['id'], 'operation': 'chat', 'payload': {'message': 'b'}}).status_code == 202
    finally:
        release.set()
        manager.pool.shutdown()
    assert not manager.active


def test_chunked_upload_stops_receiving_at_limit(client, monkeypatch):
    from starlette.requests import Request
    from sabc.request_limits import BodyLimitMiddleware, MAX_BODY_BYTES
    import asyncio
    sent, seen = [], []
    async def app(scope, receive, send):
        try:
            async for chunk in Request(scope, receive).stream(): seen.append(len(chunk))
        except HTTPException as error:
            sent.append(error.status_code)
    chunks = iter([{'type': 'http.request', 'body': b'x' * 1_000_000, 'more_body': True}] * 22)
    async def receive(): return next(chunks)
    async def send(_): pass
    asyncio.run(BodyLimitMiddleware(app)({'type': 'http', 'headers': []}, receive, send))
    assert sent == [413] and sum(seen) <= MAX_BODY_BYTES


def test_business_dates_use_shanghai_midnight(monkeypatch):
    from datetime import datetime, timezone
    from sabc import business_time, lifecycle, rating, report_readiness
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 12, 17, tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr(business_time, 'datetime', Clock)
    assert lifecycle.today().isoformat() == '2026-09-13'
    assert rating.business_today() == report_readiness.today() == checkpoints.today() == lifecycle.today()
    assert checkpoints.validation_answer('validation_history', '测试是在2026年9月13日，共100单样本', 'known', 'user', [])


def test_busy_initial_queue_preserves_successful_project_creation(client, monkeypatch):
    def busy(*_): raise module.HTTPException(429, 'busy')
    monkeypatch.setattr(module, 'start_interview', busy)
    response = client.post('/api/projects', json={'name': 'saved once', 'auto_start': True})
    assert response.status_code == 200
    assert client.get('/api/projects/' + response.json()['id']).status_code == 200
    assert len(client.get('/api/bootstrap').json()['projects']) == 1


def test_invalid_model_project_type_retries_before_saving(monkeypatch):
    import json
    import httpx
    from sabc.llm import analyze
    calls = []
    def post(self, url, **kwargs):
        calls.append(kwargs)
        content = {'reply': '请补充', 'project_patch': {'project_type': '中文类型' if len(calls) == 1 else 'internal'}}
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'choices': [{'message': {'content': json.dumps(content)}}]})
    for name in ('SABC_DEEPSEEK_API_KEY', 'SABC_MIXTOKEN_API_KEY', 'SABC_FAL_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(httpx.Client, 'post', post)
    result = analyze({'base_url': 'https://model.example/v1', 'model': 'test'}, 'synthetic', {}, {}, [], [])
    assert len(calls) == 2 and result['project_patch']['project_type'] == 'internal'


def test_twenty_mb_document_still_accepted_but_chunked_oversize_rejected(client):
    pid = client.post('/api/projects', json={'name': 'uploads'}).json()['id']
    response = client.post(f'/api/projects/{pid}/upload', files={'file': ('max.txt', b'x' * 20_000_000)})
    assert response.status_code == 200 and len(response.json()['content']) == 200000
    def chunks():
        yield b'--test\r\nContent-Disposition: form-data; name="file"; filename="large.txt"\r\n\r\n'
        for _ in range(21): yield b'x' * 1_000_000
        yield b'\r\n--test--\r\n'
    response = client.post('/api/company/import', content=chunks(),
                           headers={'Content-Type': 'multipart/form-data; boundary=test'})
    assert response.status_code == 413


def test_model_key_stays_bound_and_clear_does_not_fall_back(client, monkeypatch):
    from sabc.key_storage import model_key
    monkeypatch.setenv('SABC_MODEL_BASE_URL', 'https://original.example/v1')
    monkeypatch.setenv('SABC_API_KEY', 'synthetic')
    assert model_key({'base_url': 'https://original.example:443/v2'}) == 'synthetic'
    with pytest.raises(ValueError): model_key({'base_url': 'https://other.example/v1'})
    assert model_key({'base_url': 'http://localhost:1234', 'key_disabled': True}) == ''
    assert client.put('/api/settings', json={'base_url': 'https://original.example/v1', 'model': 'test'}).status_code == 200
    monkeypatch.setenv('SABC_UI_ORIGIN', 'https://work.example')
    assert client.put('/api/settings', json={'base_url': 'http://other.example/v1', 'model': 'test', 'clear_key': True}).status_code == 422


def test_synchronous_and_queued_work_share_actual_worker_limit(tmp_path):
    from sabc.store import Store
    store = Store(tmp_path / 'jobs.db')
    manager = Jobs()
    entered = [Event(), Event(), Event()]
    release = Event()
    def hold(index):
        entered[index].set()
        assert release.wait(3)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            direct = pool.submit(manager.execute, store, 'direct', lambda: hold(0))
            try:
                assert entered[0].wait(1)
                manager.submit(store, 'one', 'one', {}, lambda: hold(1), queue=True)
                manager.submit(store, 'two', 'two', {}, lambda: hold(2), queue=True)
                assert entered[1].wait(1)
                assert not entered[2].wait(.05)
            finally:
                release.set()
            direct.result()
    finally:
        release.set()
        manager.pool.shutdown()
    assert entered[2].is_set() and not manager.active
