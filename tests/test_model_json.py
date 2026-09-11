import json
from copy import deepcopy

import httpx
import pytest

from sabc.llm import analyze
from sabc.model_router import audit
from sabc.streaming import progress


@pytest.fixture(autouse=True)
def isolated_routes(monkeypatch):
    monkeypatch.delenv('SABC_FAL_API_KEY', raising=False)
    monkeypatch.delenv('SABC_DEEPSEEK_API_KEY', raising=False)


def serve(monkeypatch, outputs):
    calls = []
    def post(self, url, **kwargs):
        calls.append(deepcopy(kwargs['json']))
        raw = outputs[min(len(calls) - 1, len(outputs) - 1)]
        return httpx.Response(200, request=httpx.Request('POST', url),
                              json={'choices': [{'message': {'content': raw}, 'finish_reason': 'stop'}]})
    monkeypatch.setattr(httpx.Client, 'post', post)
    return calls


GOOD = '{"reply":"具体面向哪些客户？","questions":["具体面向哪些客户？"]}'
SETTINGS = {'base_url': 'https://provider.example/v1', 'model': 'glm-5.3-flash'}


@pytest.mark.parametrize('raw', [GOOD, '\n```json\n' + GOOD + '\n```\n',
                                '\ufeff  ```JSON\r\n' + GOOD + '\r\n```',
                                '  ```\n' + GOOD + '\n```  '])
def test_json_wrapping_does_not_repeat_model_call(monkeypatch, raw):
    calls = serve(monkeypatch, [raw])
    assert analyze(SETTINGS, 'test-key', {}, {}, [], [])['reply'] == '具体面向哪些客户？'
    assert len(calls) == 1


@pytest.mark.parametrize('raw,stage', [('{"reply":"未闭合', 'response_json'),
                                     (GOOD + GOOD, 'response_json'),
                                     ('解释：' + GOOD, 'response_json'),
                                     ('[]', 'response_schema'),
                                     ('{"reply":"问题","grade":"S"}', 'response_schema')])
def test_glm_retry_contains_correction_and_original_context(monkeypatch, raw, stage):
    calls = serve(monkeypatch, [raw, GOOD]); events = []
    token = audit.set(events.append)
    try:
        assert analyze(SETTINGS, 'test-key', {}, {}, [], [{'role': 'user', 'content': '原始问题'}])['reply']
    finally:
        audit.reset(token)
    assert len(calls) == 2 and calls[0]['model'] == calls[1]['model']
    assert calls[1]['messages'][:2] == calls[0]['messages']
    assert calls[1]['messages'][-2] == {'role': 'assistant', 'content': raw}
    assert '格式补正' in calls[1]['messages'][-1]['content']
    assert events[0]['error_stage'] == stage
    assert 'test-key' not in json.dumps(events)
    assert raw not in json.dumps(events, ensure_ascii=False)


def test_format_retry_is_not_carried_into_luna(monkeypatch):
    calls = serve(monkeypatch, ['bad json', 'bad json', GOOD])
    assert analyze(SETTINGS, '', {}, {}, [], [])['reply']
    assert [c['model'] for c in calls] == ['glm-5.3-flash'] * 2 + ['gpt-5.6-luna']
    assert len(calls[1]['messages']) == 4 and len(calls[2]['messages']) == 2


def test_stream_json_error_is_distinct_and_never_saved_as_reply(monkeypatch):
    from sabc.streaming import completion
    from sabc.model_router import routed
    seen = []; events = []
    ptoken = progress.set(seen.append); atoken = audit.set(events.append)
    def execute(route):
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text='data: broken-event\n\n'))) as client:
            return completion(client, 'https://model.example', {}, {}, 1)
    try:
        with pytest.raises(ValueError):
            routed('analysis', {'model': 'test'}, execute)
    finally:
        progress.reset(ptoken); audit.reset(atoken)
    assert events[0]['error_stage'] == 'stream_json'
    assert 'broken-event' not in json.dumps(events)
    assert all(value == '' for value in seen)


@pytest.mark.parametrize('first', ['\n```json\n{"reply":"依据报告说明"}\n```', '{"reply":42}'])
def test_report_assistant_uses_format_fix_and_bounded_retry(monkeypatch, first):
    from sabc import report_qa
    calls = []
    def complete(client, url, payload, headers, remaining):
        calls.append(deepcopy(payload))
        return first if len(calls) == 1 else '{"reply":"依据报告说明"}'
    monkeypatch.setattr(report_qa, 'completion', complete)
    assert report_qa.answer(SETTINGS, 'test-key', {'result': {}, 'snapshot': {}}, [], '问题') == '依据报告说明'
    if first.startswith('\n'):
        assert len(calls) == 1
    else:
        assert len(calls) == 2
        assert 'invalid_reply' in calls[1]['messages'][-1]['content']
        assert calls[1]['messages'][:3] == calls[0]['messages']


def test_fal_stream_retry_keeps_auth_and_correction(monkeypatch):
    monkeypatch.setenv('SABC_FAL_API_KEY', 'test-fal')
    calls = []; original_client = httpx.Client
    def respond(request):
        payload = json.loads(request.content); calls.append(payload)
        assert request.headers['Authorization'] == 'Key test-fal'
        assert str(request.url) == 'https://fal.run/openrouter/router/openai/v1/chat/completions'
        assert payload['stream'] is True
        raw = '{"reply":"broken' if len(calls) == 1 else '\n```json\n' + GOOD + '\n```'
        events = 'data: ' + json.dumps({'choices': [{'delta': {'content': raw}}]}) + '\n\ndata: [DONE]\n\n'
        return httpx.Response(200, text=events)
    monkeypatch.setattr('sabc.llm.httpx.Client', lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs))
    assert progress.get() is None
    assert analyze(SETTINGS, 'old-key', {}, {}, [], [])['reply']
    assert progress.get() is None
    assert len(calls) == 2
    assert calls[1]['model'] == 'z-ai/glm-5.3-flash'
    assert 'invalid_json' in calls[1]['messages'][-1]['content']
