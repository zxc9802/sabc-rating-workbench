import httpx
import pytest

from sabc.local_sources import fetch_local, save_capture, use_capture, search_local, SHANDONG_CITIES
from sabc.sources import collect
from sabc.store import Store


def test_local_query_rejects_unknown_region_and_url():
    for query in ('shenzhen/https://evil.test', 'shandong/../1', 'unknown/1'):
        with httpx.Client() as client, pytest.raises(ValueError):
            fetch_local(client, query)


@pytest.mark.parametrize('region,name,base,example',SHANDONG_CITIES)
def test_city_search_stays_on_its_configured_portal(region,name,base,example):
    seen=[]
    def respond(request):
        seen.append(str(request.url))
        assert str(request.url).startswith(base+'/catalog/')
        if request.url.path.endswith('/index'):
            return httpx.Response(200,text=f'<div><a href="{base}/catalog/{"a"*32}">人口统计</a>无条件开放</div>')
        if request.method=='GET':
            return httpx.Response(200,text='<input id="catalog" opentype="无条件开放" title="人口统计">')
        return httpx.Response(200,json={'data':[{'count':100}],'items':[{'column_name_en':'count','name_cn':'人口总数'}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result=fetch_local(client,region+'/search:人口')
    assert result['facts']['region']==region
    assert len(seen)==3


def test_search_uses_official_catalog_links_and_skips_conditional():
    page='''<div><a href="/oportal/catalog/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa">人口统计</a><span>无条件开放</span></div>
    <div><a href="https://evil.test/oportal/catalog/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb">人口恶意链接</a><span>无条件开放</span></div>
    <div><a href="/oportal/catalog/cccccccccccccccccccccccccccccccc">人口受限</a><span>有条件开放</span></div>'''
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,text=page))) as client:
        results=search_local(client,'dazhou','人口')
    assert [r['query'] for r in results]==['dazhou/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa']


def test_search_requests_unconditional_catalogs_before_pagination():
    def respond(request):
        assert request.url.params['openType']=='1'
        return httpx.Response(200,text='<div><a href="/oportal/catalog/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa">人口统计</a>无条件开放</div>')
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert len(search_local(client,'dazhou','人口'))==1


@pytest.mark.parametrize('region',['dazhou','yaan','yibin','suzhou_ah'])
def test_search_fetches_live_rows_without_saved_snapshot(region):
    seen=[]
    def respond(request):
        seen.append(str(request.url))
        if request.url.path.endswith('/index'):
            return httpx.Response(200,text='<div><a href="/oportal/catalog/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa">人口统计</a>无条件开放</div>')
        if request.method=='GET':
            return httpx.Response(200,text='<input id="catalog" opentype="无条件开放" title="人口统计">')
        return httpx.Response(200,json={'data':[{'NF':'2025','RK':123}], 'recordsTotal':5,'items':[{'name_cn':'年份','column_name_en':'NF'}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result=fetch_local(client,region+'/search:人口')
    assert result['facts']['rows']==[{'NF':'2025','RK':123}]
    assert result['facts']['selection']['keyword']=='人口'
    assert '2025' in result['period']
    assert len(seen)==3


def test_login_redirect_is_not_followed():
    calls=[]
    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(302,headers={'Location':'https://login.example/login'})
    with httpx.Client(transport=httpx.MockTransport(respond),follow_redirects=True) as client:
        with pytest.raises(ValueError,match='跳过'):
            search_local(client,'dazhou','人口')
    assert len(calls)==1


def test_personal_rows_are_skipped_for_next_aggregate_catalog():
    def respond(request):
        if request.url.path.endswith('/index'):
            return httpx.Response(200,text=''.join(f'<div><a href="/oportal/catalog/{ident*32}">人口统计</a>无条件开放</div>' for ident in ('a','b')))
        if request.method=='GET':
            return httpx.Response(200,text='<input id="catalog" opentype="无条件开放" title="人口统计">')
        if '/'+('a'*32)+'/' in request.url.path:
            return httpx.Response(200,json={'data':[{'id':'synthetic-private-id'}],'items':[{'column_name_en':'id','name_cn':'身份证号'}]})
        return httpx.Response(200,json={'data':[{'count':100}],'items':[{'column_name_en':'count','name_cn':'人口总数'}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result=fetch_local(client,'dazhou/search:人口')
    assert result['facts']['rows']==[{'count':100}]
    assert len(result['facts']['selection']['skipped'])==1
    assert 'synthetic-private-id' not in str(result)


def test_conditional_dataset_is_not_previewed():
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(200,json={'openLevelName':'有条件开放','sourceTableName':'private'})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValueError,match='无条件开放'):
            fetch_local(client,'shenzhen/29200_00403632')
    assert len(calls)==1


def test_shandong_missing_month_is_not_invented():
    def respond(request):
        if request.method=='GET':
            return httpx.Response(200,text='<input id="catalog" opentype="无条件开放" title="零售总额"><table><tr><td>数据时间范围</td><td>2020年至今</td></tr></table>')
        return httpx.Response(200,json={'data':[{'nd':'2025','jdl':'12'},{'nd':'2025','jdl':'13'}], 'recordsTotal':2,'items':[{'name_cn':'绝对量(亿元)','column_name_en':'jdl'}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        data=fetch_local(client,'shandong/20200618135541100100')
    assert data['period'].startswith('2025')
    assert '月份' in data['limitation']
    assert len(data['facts']['rows'])==2
    assert data['facts']['fields'][0]['name']=='绝对量(亿元)'


def test_capture_keeps_original_time_and_cannot_self_verify(tmp_path):
    store=Store(tmp_path/'local.db')
    capture=save_capture(store,{'region':'guangzhou','title':'机构预览','source_locator':'https://gddata.gd.gov.cn/opdata/index?id=1','data_period':'2024','scope':'广州；仅预览10行','content':'实际公开表格','retrieved_at':'2026-09-09T09:00:00+00:00','level':3,'verification_status':'verified'})
    evidence=use_capture(store,'project',capture['id'])
    assert evidence['level']==0 and evidence['verification_status']=='unverified'
    assert evidence['retrieved_at']=='2026-09-09T09:00:00+00:00'
    assert evidence['source_id']=='local' and evidence['region']=='guangzhou'
    assert store.list('source_runs')[0]['method']=='browser-observation'
    with pytest.raises(ValueError):
        save_capture(store,{**capture,'source_locator':'https://gddata.gd.gov.cn.evil.test/a'})


def test_local_failure_is_audited_and_retries_bounded(tmp_path,monkeypatch):
    store=Store(tmp_path/'local.db')
    def fail(*args,**kwargs): raise httpx.ConnectError('offline')
    monkeypatch.setattr(httpx.Client,'get',fail)
    with pytest.raises(ValueError,match='3 次'):
        collect(store,'p','local','shandong/20200618135541100100')
    assert len(store.list('source_runs'))==3
    assert not store.list('evidence')
