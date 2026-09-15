import json

import httpx
import pytest

from sabc.model_router import routed, authorization, endpoint
from sabc.streaming import completion, progress


@pytest.mark.parametrize('role', ['analysis', 'report_chat'])
def test_gemini_first_with_luna_key_and_existing_fallbacks(monkeypatch, role):
    monkeypatch.setenv('SABC_FAL_API_KEY', 'fal-test-key')
    monkeypatch.setenv('SABC_DEEPSEEK_API_KEY', 'deepseek-test-key')
    calls = []
    def execute(route):
        calls.append(route)
        if len(calls) == 1:
            assert endpoint(route) == 'https://api.openlux.ai/v1beta/models/gemini-3.8-flash:generateContent'
            assert authorization(route, route['key']) == {'x-goog-api-key': 'luna-test-key'}
        if route.get('deepseek'):
            return 'ok'
        raise httpx.ConnectError('failed')
    assert routed(role, {'base_url': 'https://api.openlux.ai/v1', 'model': 'glm-5.3-flash',
                         'key': 'luna-test-key'}, execute) == 'ok'
    assert [route['model'] for route in calls] == [
        'gemini-3.8-flash', 'z-ai/glm-5.3-flash', 'z-ai/glm-5.3-flash', 'gpt-5.6-luna', 'deepseek-flash']
    assert [route['primary'] for route in calls] == [True, False, False, False, False]
    assert calls[3]['key'] == 'luna-test-key'
    assert 'endpoint' not in calls[3] and 'auth_scheme' not in calls[3]


def test_native_payload_and_no_unvalidated_preview():
    seen = []
    def transport(request):
        body = json.loads(request.content)
        assert body['systemInstruction']['parts'] == [{'text': '规则'}]
        assert [turn['role'] for turn in body['contents']] == ['user', 'model', 'user']
        assert body['generationConfig'] == {'responseMimeType': 'application/json', 'temperature': 0.1,
                                             'maxOutputTokens': 3000}
        assert 'stream' not in body and 'model' not in body
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
            {'thought': True, 'text': 'hidden'}, {'text': '{"reply":"回答"}'}]}}]})
    token = progress.set(seen.append)
    try:
        with httpx.Client(transport=httpx.MockTransport(transport)) as client:
            result = completion(client, 'https://example.test/model:generateContent', {
                'messages': [{'role': role, 'content': text} for role, text in [
                    ('system', '规则'), ('user', '问题'), ('assistant', '追问'), ('user', '补充')]],
                'temperature': 0.1, 'max_tokens': 3000}, {}, 10)
    finally:
        progress.reset(token)
    assert result == '{"reply":"回答"}' and seen == []


@pytest.mark.parametrize('response', [
    {'candidates': []},
    {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': '{"reply":"半截"}'}]}}]},
    {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'thought': True, 'text': 'hidden'}]}}]},
])
def test_incomplete_native_response_is_rejected(response):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))) as client:
        with pytest.raises(ValueError):
            completion(client, 'https://example.test/model:generateContent', {'messages': []}, {}, 10)
