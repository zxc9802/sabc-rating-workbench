import httpx
import pytest

from scripts.probe_local_platforms import probe


@pytest.mark.parametrize('target,status',[
    ('https://new.example/open','redirect_unverified'),
    ('https://new.example/login','skipped_login'),
])
def test_html_migration_notice_is_not_reported_as_working_platform(monkeypatch,target,status):
    calls=[]
    def get(self,url,**kwargs):
        calls.append(url)
        return httpx.Response(200,text=f'<title>平台已迁移</title><meta http-equiv="refresh" content="10;url={target}">',request=httpx.Request('GET',url))
    monkeypatch.setattr(httpx.Client,'get',get)
    result=probe({'name':'候选站点','url':'https://old.example/'},1)
    assert result['status']==status
    assert result['redirect']==target
    assert result['redirect_method']=='html-meta-refresh'
    assert len(calls)==1
