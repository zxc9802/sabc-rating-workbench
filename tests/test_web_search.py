import httpx
import pytest
from sabc.sources import collect
from sabc.store import Store


def test_search_saves_only_unverified_snippets(tmp_path, monkeypatch):
    monkeypatch.setenv('ANYSEARCH_API_KEY', 'secret-test')
    monkeypatch.setenv('SABC_COLLECTOR_URL', 'https://collector.invalid')
    def post(self, url, **kwargs):
        assert url == 'https://api.anysearch.com/v1/search'
        assert kwargs['headers']['Authorization'] == 'Bearer secret-test'
        return httpx.Response(200, json={'code':0,'data':{'results':[
            {'title':'Official', 'url':'https://go.dev/doc/go1.26','snippet':'Release notes'},
            {'url':'javascript:alert(1)','snippet':'bad'}]}})
    monkeypatch.setattr(httpx.Client, 'post', post)
    s=Store(tmp_path/'x.db')
    e=collect(s,'p','web','Go release notes')
    assert e['level']==0 and e['verification_status']=='unverified'
    assert 'https://go.dev/doc/go1.26' in e['content']
    assert 'javascript:' not in e['content'] and '未读取网页全文' in e['content']


@pytest.mark.parametrize('status,payload', [(401,{}),(429,{}),(200,{'code':1}),(200,{'code':0,'data':{'results':[]}})])
def test_failed_search_never_creates_evidence(tmp_path, monkeypatch, status, payload):
    monkeypatch.setenv('ANYSEARCH_API_KEY','secret-test')
    monkeypatch.setattr(httpx.Client,'post',lambda *a,**k:httpx.Response(status,json=payload))
    s=Store(tmp_path/'x.db')
    with pytest.raises(ValueError):collect(s,'p','web','test')
    assert not s.list('evidence')
    assert len(s.list('source_runs'))==1
