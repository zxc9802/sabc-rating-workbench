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


def test_four_primary_attempts_fallback_and_reset_next_request(primary):
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
    assert calls==(['deepseek-flash']*4+['old-model'])*2
    assert [e['attempt'] for e in events]==[1,2,3,4,1]*2
    assert 'synthetic-primary-key' not in json.dumps(events)


def test_primary_success_does_not_call_legacy(primary):
    calls=[]
    def execute(route): calls.append(route);return 'ok'
    assert routed('planner',{'model':'old'},execute)=='ok'
    assert len(calls)==1 and calls[0]['effort']=='max'


def test_schema_failure_retries_primary_then_original_analysis(primary,monkeypatch):
    calls=[]
    def post(self,url,**kwargs):
        payload=kwargs['json'];calls.append(payload)
        content='bad json' if payload['model']=='deepseek-flash' else '{"reply":"继续原来的访谈","proposal":null}'
        return httpx.Response(200,request=httpx.Request('POST',url),json={'choices':[{'message':{'content':content}}]})
    monkeypatch.setattr(httpx.Client,'post',post)
    answer=analyze({'base_url':'https://old.example/v1','model':'gpt-5.6-luna'},'old-key',{}, {},[],[])
    assert answer['reply']=='继续原来的访谈'
    assert [c['model'] for c in calls]==['deepseek-flash']*4+['gpt-5.6-luna']
    assert all(c['thinking']=={'type':'enabled'} and c['reasoning_effort']=='max' for c in calls[:4])
    assert 'thinking' not in calls[4]


def test_planner_bad_query_falls_back_without_fetching(primary,monkeypatch):
    calls=[]
    def post(self,url,**kwargs):
        payload=kwargs['json'];calls.append(payload['model'])
        requests=[{'source':'github','query':'invented/repo','reason':'test'}] if payload['model']=='deepseek-flash' else []
        return httpx.Response(200,request=httpx.Request('POST',url),json={'choices':[{'message':{'content':json.dumps({'reason':'仅整理内部资料','data_requests':requests})}}]})
    monkeypatch.setattr(httpx.Client,'post',post)
    assert planner.plan_search({}, {}, [], [])['data_requests']==[]
    assert calls==['deepseek-flash']*4+['glm-5.3-flash']


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
    assert calls==['deepseek-flash']*4+['old']
