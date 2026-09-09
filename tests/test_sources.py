import httpx
import pytest

from sabc.sources import collect, request_spec, normalize
from sabc.store import Store


def test_query_cannot_change_api_host():
    for source, query in [('github','https://evil.test'),('sec','../x'),('worldbank','CHN/../../x')]:
        with pytest.raises(ValueError): request_spec(source,query)


def test_empty_results_are_not_evidence():
    with pytest.raises(ValueError): normalize('apple',{'results':[]},'us/missing')
    with pytest.raises(ValueError): normalize('worldbank',[{},[]],'CHN/X')


def test_trends_preserves_period_and_does_not_claim_history():
    xml=b'<rss xmlns:ht="https://trends.google.com/trending/rss"><channel><item><title>test</title><pubDate>Wed, 09 Sep 2026 08:00:00 GMT</pubDate><ht:approx_traffic>500+</ht:approx_traffic></item></channel></rss>'
    _,_,rows,limitation=normalize('trends',xml,'US')
    assert rows[0]['approx_traffic']=='500+'
    assert rows[0]['published_at']=='Wed, 09 Sep 2026 08:00:00 GMT'
    assert '不是指定关键词历史指数' in limitation
    with pytest.raises(ValueError): request_spec('trends','US/notion')


def test_law_search_preserves_status_and_removes_markup():
    _,_,facts,_=normalize('law',{'code':200,'rows':[{'bbbs':'abc','title':'<em>法律</em>','sxx':1,'gbrq':'2021-01-01','sxrq':'2021-02-01'}]},'法律')
    assert facts['rows'][0]['title']=='法律'
    assert facts['rows'][0]['sxx']==1
    assert facts['rows'][0]['detail_url'].endswith('?id=abc')


def test_law_directory_alone_is_not_full_text():
    with pytest.raises(ValueError): normalize('law',{'code':200,'data':{'title':'法','content':{'title':'第一条'}}},'id:abcdefghij')


def test_official_article_rejects_login_or_homepage():
    with pytest.raises(ValueError): normalize('stats','<title>登录</title><body>请验证</body>','https://www.stats.gov.cn/a.html')
    with pytest.raises(ValueError): request_spec('miit','https://www.miit.gov.cn.evil.test/a.html')


def test_sec_facts_preserves_period_and_unit():
    raw={'entityName':'Test','facts':{'us-gaap':{'NetIncomeLoss':{'units':{'USD':[{'start':'2025-01-01','end':'2025-12-31','val':20,'form':'10-K','filed':'2026-02-01','accn':'test'}]}}}}}
    _,period,rows,_=normalize('sec',raw,'1/facts')
    assert period=='2025-12-31'
    assert rows[0]['unit']=='USD' and rows[0]['start']=='2025-01-01' and rows[0]['accn']=='test'


def test_retry_limit_and_failure_audit(tmp_path,monkeypatch):
    store=Store(tmp_path/'test.db')
    def fail(*args,**kwargs): raise httpx.ConnectError('test outage')
    monkeypatch.setattr(httpx.Client,'get',fail)
    with pytest.raises(ValueError,match='3 次'): collect(store,'p','github','a/b')
    assert len(store.list('source_runs'))==3
    assert not store.list('evidence')


def test_rate_limit_defers_without_hammering(tmp_path,monkeypatch):
    store=Store(tmp_path/'test.db')
    def limited(*args,**kwargs): return httpx.Response(429,request=httpx.Request('GET','https://api.github.com/repos/a/b'))
    monkeypatch.setattr(httpx.Client,'get',limited)
    with pytest.raises(ValueError): collect(store,'p','github','a/b')
    assert len(store.list('source_runs'))==1


def test_success_is_persisted_but_not_automatically_verified(tmp_path,monkeypatch):
    store=Store(tmp_path/'test.db')
    def success(*args,**kwargs): return httpx.Response(200,json={'full_name':'a/b','stargazers_count':100},request=httpx.Request('GET','https://api.github.com/repos/a/b'))
    monkeypatch.setattr(httpx.Client,'get',success)
    e=collect(store,'p','github','a/b')
    assert e['verification_status']=='unverified' and e['level']==0
    assert store.get('evidence',e['id'])['payload_sha256']
    assert store.list('source_runs')[0]['evidence_id']==e['id']
