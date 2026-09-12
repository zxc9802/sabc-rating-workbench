import json
import httpx
import pytest
from sabc import model_router, report_qa
from sabc.llm import analyze


@pytest.fixture
def mixtoken(monkeypatch):
    monkeypatch.setenv('SABC_MIXTOKEN_API_KEY', 'synthetic-mixtoken')
    monkeypatch.setenv('SABC_FAL_API_KEY', 'synthetic-fal')
    monkeypatch.setenv('SABC_DEEPSEEK_API_KEY', 'synthetic-deepseek')
    return {'base_url': 'https://api.openlux.ai/v1', 'model': 'glm-5.3-flash', 'key': 'synthetic-openlux'}


@pytest.mark.parametrize('role', ['analysis', 'report_chat'])
def test_mixtoken_first_preserves_full_fallback_order(mixtoken, role):
    calls=[]; events=[]
    def execute(route):
        calls.append(route)
        if route['deepseek']: return 'ok'
        raise ValueError('unavailable')
    token=model_router.audit.set(events.append)
    try:
        assert model_router.routed(role, mixtoken, execute)=='ok'
    finally:
        model_router.audit.reset(token)
    assert [r['model'] for r in calls]==['deepseek-v4.1-flash','gemini-3.8-flash',
        'z-ai/glm-5.3-flash','z-ai/glm-5.3-flash','gpt-5.6-luna','deepseek-flash']
    assert [r['primary'] for r in calls]==[True,False,False,False,False,False]
    assert model_router.endpoint(calls[0])=='https://api.mixtoken.ai/v1/chat/completions'
    assert model_router.authorization(calls[0],calls[0]['key'])=={'Authorization':'Bearer synthetic-mixtoken'}
    assert calls[4]['key']=='synthetic-openlux'
    assert all('synthetic-' not in json.dumps(event) for event in events)


@pytest.mark.parametrize('kind', ['interview', 'report', 'qa'])
def test_mixtoken_uses_real_sse_without_visible_callback(mixtoken, monkeypatch, kind):
    calls=[]
    def transport(request):
        payload=json.loads(request.content); calls.append(payload)
        assert str(request.url)=='https://api.mixtoken.ai/v1/chat/completions'
        assert payload['model']=='deepseek-v4.1-flash' and payload['stream'] is True
        assert 'reasoning_effort' not in payload and 'thinking' not in payload
        raw=json.dumps({'reply':'回答完成','proposal':None} if kind!='qa' else {'reply':'依据不足，不能确定'})
        events=''.join('data: '+json.dumps({'choices':[{'delta':{'content':c}}]})+'\n\n' for c in raw)
        return httpx.Response(200, text=events+'data: [DONE]\n\n', headers={'content-type':'text/event-stream'})
    original=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(transport), **kwargs))
    if kind=='qa':
        assert report_qa.answer({},'',{'snapshot':{},'result':{}},[],'缺失报价是多少？')=='依据不足，不能确定'
    else:
        assert analyze(mixtoken,mixtoken['key'],{'_report_requested':kind=='report'}, {},[],[])['reply']=='回答完成'
    assert len(calls)==1
