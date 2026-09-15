"""Content corrections stay with their author; only provider failures switch routes."""
from copy import deepcopy
from threading import Event
from types import SimpleNamespace
import json

import httpx
import pytest
from sabc import advisory, llm, model_router, report_qa
from sabc.model_output import ModelResponseError, format_failure
from sabc.streaming import JobCancelled, cancel_signal
from tests.test_advisory_payload import context as report_context
from tests.test_hidden_review import accepted
from tests.test_report_timeouts import report_input


@pytest.fixture
def clock(monkeypatch):
    now = [100.0]
    timer = SimpleNamespace(monotonic=lambda: now[0])
    for module in (model_router, llm, advisory, report_qa):
        monkeypatch.setattr(module, 'time', timer)
    monkeypatch.setenv('SABC_MIXTOKEN_API_KEY', 'synthetic-primary')
    monkeypatch.setenv('SABC_DEEPSEEK_API_KEY', 'synthetic-backup')
    monkeypatch.delenv('SABC_FAL_API_KEY', raising=False)
    return now


@pytest.mark.parametrize('kind', ['interview', 'report', 'review', 'report_chat'])
def test_multiple_content_corrections_never_leave_primary(monkeypatch, clock, kind):
    project, company, evidence, reply = report_input()
    seen = []
    def completion(client, url, payload, headers, remaining):
        seen.append(deepcopy(payload))
        clock[0] += 10
        assert headers['Authorization'] == 'Bearer synthetic-primary'
        if len(seen) > 1:
            assert '补正' in payload['messages'][-1]['content']
        if kind == 'interview':
            result = {'reply': '还有哪些投入？', 'project_patch': {'budget_requested': -1 if len(seen) < 5 else 3000}}
        elif kind == 'report':
            result = deepcopy(reply)
            if len(seen) < 5:
                result['proposal']['dimensions']['risk']['reason'] = ''
        elif kind == 'review':
            result = accepted()
            if len(seen) < 5:
                result['coverage_reasons'] = {'invented_dimension': '不存在的维度'}
        else:
            result = {'reply': 42 if len(seen) < 5 else '依据报告说明'}
        return json.dumps(result)
    module = {'interview': llm, 'report': llm, 'review': advisory, 'report_chat': report_qa}[kind]
    monkeypatch.setattr(module, 'completion', completion)
    if kind == 'interview':
        assert llm.analyze({}, '', {}, {}, [], [])['project_patch']['budget_requested'] == 3000
    elif kind == 'report':
        assert llm.analyze({}, '', project, company, evidence, [])['proposal']
    elif kind == 'review':
        assert advisory._request({}, '', report_context())['checks']['facts'] == 'pass'
    else:
        assert report_qa.answer({}, '', {'snapshot': {}, 'result': {}}, [], '原因') == '依据报告说明'
    assert [p['model'] for p in seen] == ['deepseek-v4.1-flash'] * 5
    assert all(p['messages'][1] == seen[0]['messages'][1] for p in seen)
    if kind == 'review':
        assert all('后台质量审查者' in p['messages'][0]['content'] for p in seen)
    else:
        assert all(p['messages'][0]['content'].startswith(seen[0]['messages'][0]['content']) for p in seen)


@pytest.mark.parametrize('failure', [httpx.ReadTimeout('slow'), httpx.ConnectError('offline'),
    *[ModelResponseError('upstream failed', stage) for stage in (
        'http', 'timeout', 'transport_json', 'transport_schema', 'stream_json',
        'stream_transport', 'response_incomplete')]])
def test_provider_failure_after_content_corrections_allows_fallback(clock, failure):
    seen = []
    def execute(route):
        seen.append(deepcopy(route))
        clock[0] += 10
        if len(seen) <= 2:
            raise format_failure(ValueError('引用不匹配'), f'draft-{len(seen)}')
        if len(seen) == 3:
            raise failure
        return 'backup result'
    assert model_router.routed('analysis', {}, execute) == 'backup result'
    assert [r['model'] for r in seen] == ['deepseek-v4.1-flash'] * 3 + ['deepseek-flash']
    assert seen[2]['format_retry'][-2]['content'] == 'draft-2'
    assert len({r['correction_deadline'] for r in seen[:3]}) == 1
    assert seen[3]['correction_deadline'] > seen[2]['correction_deadline']


def test_only_content_failures_exhaust_budget_without_switching(clock):
    seen = []; deadlines = []
    def execute(route):
        seen.append(route['model'])
        deadlines.append(route['correction_deadline'])
        clock[0] += 100
        raise format_failure(ValueError('来源仍不匹配'), 'synthetic draft')
    with pytest.raises(ModelResponseError, match='来源仍不匹配') as error:
        model_router.routed('analysis', {'request_timeout': 300}, execute)
    assert error.value.stage == 'response_validation'
    assert seen == ['deepseek-v4.1-flash'] * 3
    assert deadlines == [400] * 3


def test_cancel_during_correction_does_not_retry_or_switch(clock):
    signal = Event(); seen = []
    def execute(route):
        seen.append(route['model'])
        signal.set()
        raise format_failure(ValueError('内容待修订'), 'draft')
    token = cancel_signal.set(signal)
    try:
        with pytest.raises(JobCancelled):
            model_router.routed('review', {}, execute)
    finally:
        cancel_signal.reset(token)
    assert seen == ['deepseek-v4.1-flash']


@pytest.mark.parametrize('failure', [ValueError('local validation'), TypeError('coding error'),
                                   ModelResponseError('unknown error', 'unknown')])
def test_unclassified_errors_do_not_trigger_provider_fallback(clock, failure):
    seen = []
    def execute(route):
        seen.append(route['model'])
        raise failure
    with pytest.raises(type(failure)):
        model_router.routed('review', {}, execute)
    assert seen == ['deepseek-v4.1-flash']
