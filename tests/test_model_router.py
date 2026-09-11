import json
import httpx
import pytest
from sabc.model_router import routed, audit
from sabc import planner
from sabc.llm import analyze
from sabc.streaming import progress


@pytest.fixture
def primary(monkeypatch):
    monkeypatch.setenv('SABC_DEEPSEEK_API_KEY', 'synthetic-primary-key')
    monkeypatch.setenv('SABC_PLANNER_API_KEY', 'synthetic-legacy-key')
    monkeypatch.setattr('sabc.model_router.time.sleep', lambda _: None)


def test_preferred_then_deepseek_and_reset_next_request(primary):
    calls=[];events=[]
    def execute(route):
        calls.append(route['model'])
        if route['primary']: raise ValueError('upstream failure')
        return 'legacy answer'
    token=audit.set(events.append)
    try:
        assert routed('analysis',{'model':'old-model'},execute)=='legacy answer'
        assert routed('analysis',{'model':'old-model'},execute)=='legacy answer'
    finally:audit.reset(token)
    assert calls==['old-model','deepseek-flash']*2
    assert [e['attempt'] for e in events]==[1,1]*2
    assert 'synthetic-primary-key' not in json.dumps(events)


def test_primary_success_does_not_call_legacy(primary):
    calls=[]
    def execute(route): calls.append(route);return 'ok'
    assert routed('planner',{'model':'old'},execute)=='ok'
    assert len(calls)==1 and calls[0]['model']=='old' and not calls[0]['deepseek']


def test_schema_failure_retries_primary_then_original_analysis(primary,monkeypatch):
    calls=[]
    def post(self,url,**kwargs):
        payload=kwargs['json'];calls.append(payload)
        content='bad json' if payload['model']!='deepseek-flash' else '{"reply":"继续原来的访谈","proposal":null}'
        return httpx.Response(200,request=httpx.Request('POST',url),json={'choices':[{'message':{'content':content}}]})
    monkeypatch.setattr(httpx.Client,'post',post)
    answer=analyze({'base_url':'https://old.example/v1','model':'gpt-5.6-luna'},'old-key',{}, {},[],[])
    assert answer['reply']=='继续原来的访谈'
    assert [c['model'] for c in calls]==['gpt-5.6-luna']*2+['deepseek-flash']
    assert all(c['thinking']=={'type':'enabled'} and c['reasoning_effort']=='max' for c in calls[2:])
    assert 'thinking' not in calls[0]



def test_partial_primary_answer_is_cleared_before_fallback(primary):
    seen=[]
    def execute(route):
        if route['primary']:
            progress.get()('不完整的内容')
            raise ValueError('interrupted')
        assert seen[-1]==''
        return 'complete'
    token=progress.set(seen.append)
    try:assert routed('analysis',{'model':'old'},execute)=='complete'
    finally:progress.reset(token)


def test_all_models_fail_without_sticky_route(primary):
    calls=[]
    def fail(route): calls.append(route['model']);raise ValueError('failed')
    with pytest.raises(ValueError):routed('analysis',{'model':'old'},fail)
    assert calls==['old','deepseek-flash']


@pytest.mark.parametrize('success_at', [1, 2, 3, 4, None])
def test_glm_retry_luna_same_provider_then_deepseek(primary, success_at):
    calls=[];events=[]
    def execute(route):
        calls.append(route)
        if len(calls)==success_at: return 'ok'
        raise ValueError('model failed')
    token=audit.set(events.append)
    try:
        if success_at:
            assert routed('review',{'model':'glm-5.3-flash','base_url':'https://provider.example/v1','key':'synthetic-shared'},execute)=='ok'
        else:
            with pytest.raises(ValueError):
                routed('review',{'model':'glm-5.3-flash','base_url':'https://provider.example/v1','key':'synthetic-shared'},execute)
    finally:audit.reset(token)
    assert [r['model'] for r in calls]==['glm-5.3-flash','glm-5.3-flash','gpt-5.6-luna','deepseek-flash'][:success_at or 4]
    assert [r['attempt'] for r in events][:2]==[1,2][:min(success_at or 4,2)]
    for r in calls[:3]:
        assert r['base_url']=='https://provider.example/v1' and r['key']=='synthetic-shared'
    assert 'synthetic-shared' not in json.dumps(events)


def test_glm_invalid_json_only_retries_once_before_luna(primary,monkeypatch):
    calls=[]
    def post(self,url,**kwargs):
        model=kwargs['json']['model'];calls.append(model)
        content='bad json' if model.startswith('glm') else '{"reply":"继续访谈","proposal":null}'
        return httpx.Response(200,request=httpx.Request('POST',url),json={'choices':[{'message':{'content':content}}]})
    monkeypatch.setattr(httpx.Client,'post',post)
    assert analyze({'base_url':'https://provider.example/v1','model':'glm-5.3-flash'},'synthetic-key',{}, {},[],[])['reply']=='继续访谈'
    assert calls==['glm-5.3-flash','glm-5.3-flash','gpt-5.6-luna']


def test_cancel_does_not_retry_or_fallback(primary):
    from sabc.streaming import JobCancelled
    calls=[]
    def execute(route):
        calls.append(route['model'])
        raise JobCancelled()
    with pytest.raises(JobCancelled):
        routed('review',{'model':'glm-5.3-flash'},execute)
    assert calls==['glm-5.3-flash']
