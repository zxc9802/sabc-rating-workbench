import json
from threading import Event

import httpx
import pytest

import sabc.app as app_module
from sabc import company_import
from tests.test_app import client
from tests.test_jobs import terminal
from tests.test_sso import setup, client_for


DOCUMENT = '公司名称：青禾科技。新项目可用预算8万元人民币。团队为2名工程师，每人每周10小时。'
FIELDS = {'name': '青禾科技', 'budget': 80000, 'team': '2名工程师，每人每周10小时'}
SOURCES = {'name': '公司名称：青禾科技', 'budget': '新项目可用预算8万元人民币', 'team': '团队为2名工程师，每人每周10小时'}
SETTINGS = {'base_url': 'https://model.example/v1', 'model': 'configured-primary'}


@pytest.fixture(autouse=True)
def model(monkeypatch):
    for key in ('SABC_MIXTOKEN_API_KEY', 'SABC_DEEPSEEK_API_KEY', 'SABC_FAL_API_KEY', 'SABC_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(app_module, 'settings', lambda: SETTINGS)
    monkeypatch.setattr(company_import, 'completion', lambda *args: json.dumps({'fields': FIELDS, 'sources': SOURCES, 'warnings': []}))


def test_import_runs_in_background_and_does_not_save_or_confirm_company(client, monkeypatch):
    saved = client.put('/api/company', json={'name': '原公司', 'cash_available': 120000, 'confirmed': True}).json()
    started, release = Event(), Event()
    def complete(*args):
        started.set()
        assert release.wait(3)
        return json.dumps({'fields': FIELDS, 'sources': SOURCES, 'warnings': []})
    monkeypatch.setattr(company_import, 'completion', complete)
    try:
        response = client.post('/api/company/import', files={'file': ('公司资料.txt', DOCUMENT.encode())})
        assert response.status_code == 202
        assert started.wait(1)
        assert response.json()['status'] == 'running'
        assert client.get('/api/bootstrap').json()['company'] == saved
    finally:
        release.set()
    result = terminal(client, response.json()['id'])
    assert result['status'] == 'success'
    assert result['result']['fields'] == FIELDS
    assert 'cash_available' not in result['result']['fields']
    assert client.get('/api/bootstrap').json()['company'] == saved
    assert client.get('/api/bootstrap').json()['projects'] == []


def test_uses_same_mixtoken_primary_as_project_analysis(monkeypatch):
    monkeypatch.setenv('SABC_MIXTOKEN_API_KEY', 'synthetic-key')
    monkeypatch.setenv('SABC_MIXTOKEN_MODEL', 'configured-first-model')
    calls = []
    def complete(client, url, payload, headers, remaining):
        calls.append((url, payload, headers))
        return json.dumps({'fields': FIELDS, 'sources': SOURCES})
    monkeypatch.setattr(company_import, 'completion', complete)
    result = company_import.analyze_document(DOCUMENT, SETTINGS, '')
    assert result['fields']['budget'] == 80000
    assert len(calls) == 1
    assert calls[0][1]['model'] == 'configured-first-model'
    assert calls[0][1]['stream'] is True
    assert calls[0][2]['Authorization'] == 'Bearer synthetic-key'


def test_primary_failure_uses_existing_fallback(monkeypatch):
    monkeypatch.setenv('SABC_DEEPSEEK_API_KEY', 'synthetic-fallback-key')
    calls = []
    def complete(client, url, payload, headers, remaining):
        calls.append(payload['model'])
        if len(calls) == 1:
            raise httpx.ConnectError('synthetic failure')
        return json.dumps({'fields': FIELDS, 'sources': SOURCES})
    monkeypatch.setattr(company_import, 'completion', complete)
    assert company_import.analyze_document(DOCUMENT, SETTINGS, '')['fields'] == FIELDS
    assert calls == ['configured-primary', 'deepseek-flash']


@pytest.mark.parametrize('invalid', [
    {'fields': {'confirmed': True}, 'sources': {}},
    {'fields': {'budget': -1}, 'sources': SOURCES},
    {'fields': {'budget': True}, 'sources': SOURCES},
    {'fields': {'budget': '8万元'}, 'sources': SOURCES},
    {'fields': {'name': '无依据公司'}, 'sources': {'name': '不存在的原文'}},
])
def test_invalid_output_is_corrected_before_any_fields_are_returned(monkeypatch, invalid):
    calls = []
    def complete(client, url, payload, headers, remaining):
        calls.append(payload)
        return json.dumps(invalid if len(calls) == 1 else {'fields': FIELDS, 'sources': SOURCES})
    monkeypatch.setattr(company_import, 'completion', complete)
    assert company_import.analyze_document(DOCUMENT, SETTINGS, '')['fields'] == FIELDS
    assert len(calls) == 2
    assert '格式补正' in calls[1]['messages'][-1]['content']


def test_unknown_fields_are_omitted_but_explicit_zero_is_preserved(monkeypatch):
    monkeypatch.setattr(company_import, 'completion', lambda *args: json.dumps({
        'fields': {'name': None, 'budget': 0, 'team': ''}, 'sources': {'budget': '新项目预算为0元'}}))
    assert company_import.analyze_document('新项目预算为0元', SETTINGS, '')['fields'] == {'budget': 0}


@pytest.mark.parametrize('text', ['', ' ' * 3, '字' * 60001])
def test_unreadable_or_oversized_text_is_rejected_before_model(monkeypatch, text):
    monkeypatch.setattr(company_import, 'completion', lambda *args: pytest.fail('must not call model'))
    with pytest.raises(ValueError): company_import.analyze_document(text, SETTINGS, '')


def test_invalid_files_leave_company_unchanged(client):
    assert client.post('/api/company/import', files={'file': ('bad.exe', b'hello')}).status_code == 422
    assert client.post('/api/company/import', files={'file': ('large.txt', b'a' * 20_000_001)}).status_code == 422
    response = client.post('/api/company/import', files={'file': ('empty.txt', b'')})
    result = terminal(client, response.json()['id'])
    assert result['status'] == 'failed'
    assert '未读取到文字' in result['error']
    assert client.get('/api/bootstrap').json()['company'] == {}


def test_company_import_job_is_only_visible_to_its_account(setup):
    a, b = client_for('company-import-a'), client_for('company-import-b')
    response = a.post('/api/company/import', files={'file': ('公司.txt', DOCUMENT.encode())})
    assert response.status_code == 202
    ident = response.json()['id']
    assert b.get('/api/jobs/' + ident).status_code == 404
    assert terminal(a, ident)['result']['fields'] == FIELDS
    assert a.get('/api/bootstrap').json()['company'] == {}
