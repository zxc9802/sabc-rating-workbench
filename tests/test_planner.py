import json

import httpx
import pytest

from sabc import planner


def mock_plan(monkeypatch, requests):
    monkeypatch.setenv('SABC_PLANNER_API_KEY', 'test-only-key')
    def post(self, url, **kwargs):
        assert kwargs['json']['model'] == 'glm-5.3-flash'
        assert 'aksu/gdp:2025' in kwargs['json']['messages'][1]['content']
        payload = {'reason': '核实技术依赖', 'data_requests': requests}
        return httpx.Response(200, request=httpx.Request('POST', url),
                              json={'choices': [{'message': {'content': json.dumps(payload)}}]})
    monkeypatch.setattr(httpx.Client, 'post', post)


def test_grounded_repository_and_no_search_explanation(monkeypatch):
    mock_plan(monkeypatch, [{'source': 'github', 'query': 'fastapi/fastapi', 'reason': '核验依赖'}])
    result = planner.plan_search({}, {}, [], [{'role': 'user', 'content': '检查fastapi/fastapi'}])
    assert result['data_requests'][0]['query'] == 'fastapi/fastapi'
    mock_plan(monkeypatch, [])
    assert planner.plan_search({}, {}, [], [])['reason']


@pytest.mark.parametrize('source,query', [('github', 'invented/repo'), ('sec', '123456/facts'),
                                         ('local', 'shandong/' + '1' * 20),
                                         ('stats', 'https://www.stats.gov.cn/imaginary.html')])
def test_ungrounded_model_identifier_never_reaches_collector(monkeypatch, source, query):
    mock_plan(monkeypatch, [{'source': source, 'query': query, 'reason': '核验'}])
    with pytest.raises(ValueError, match='不存在的标识'):
        planner.plan_search({}, {}, [], [])


def test_unknown_region_and_duplicate_query_rejected(monkeypatch):
    mock_plan(monkeypatch, [{'source': 'local', 'query': 'unknown/search:人口', 'reason': '核验'}])
    with pytest.raises(ValueError):
        planner.plan_search({}, {}, [], [])
    request = {'source': 'apple', 'query': 'cn/笔记', 'reason': '核验应用'}
    mock_plan(monkeypatch, [request, request])
    with pytest.raises(ValueError, match='重复查询'):
        planner.plan_search({}, {}, [], [])


def test_http_failure_does_not_leak_provider_body_or_key(monkeypatch):
    monkeypatch.setenv('SABC_PLANNER_API_KEY', 'test-only-key')
    def fail(self, url, **kwargs):
        return httpx.Response(401, text='test-only-key', request=httpx.Request('POST', url))
    monkeypatch.setattr(httpx.Client, 'post', fail)
    with pytest.raises(ValueError, match='HTTP 401') as error:
        planner.plan_search({}, {}, [], [])
    assert 'test-only-key' not in str(error.value)


def test_provider_json_fence_is_accepted_without_accepting_surrounding_prose(monkeypatch):
    monkeypatch.setenv('SABC_PLANNER_API_KEY', 'test-only-key')
    content='```json\n{"reason":"无需取数","data_requests":[]}\n```'
    def post(self,url,**kwargs):
        return httpx.Response(200,request=httpx.Request('POST',url),json={'choices':[{'message':{'content':content}}]})
    monkeypatch.setattr(httpx.Client,'post',post)
    assert planner.plan_search({}, {}, [], [])['data_requests']==[]
    content='额外内容'+content
    with pytest.raises(ValueError,match='未返回有效查询计划'):
        planner.plan_search({}, {}, [], [])
