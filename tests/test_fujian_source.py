import httpx
import pytest

from sabc.local_sources import fetch_local, FUJIAN_CITIES


def test_fujian_search_reads_preview_and_retains_scope():
    def respond(request):
        assert request.url.host=='data.fujian.gov.cn'
        path=request.url.path
        if path.endswith('/list'):
            assert request.url.params['key']=='森林公园'
            data={'rows':[{'catalogID':'A'*32,'catalogName':'森林公园','openType':'1'}]}
        elif path.endswith('/getCataInfo'):
            data={'catalogName':'森林公园','orgName':'三明市林业局','openType':'1','dataVol':500,'dataUpdateTime':'2026-09-01'}
        elif path.endswith('/getCataItem'):
            data=[{'nameEn':'mc','nameCn':'名称'}]
        else:
            assert path.endswith('/getCataItemData')
            data={'rows':[{'mc':str(i)} for i in range(35)],'total':35}
        return httpx.Response(200,json={'code':200,'data':data})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result=fetch_local(client,'fujian/search:森林公园')
    assert result['facts']['retrieved_rows']==30
    assert result['facts']['reported_total']==500
    assert result['facts']['metadata']['orgName']=='三明市林业局'
    assert '不等于数据期间' in result['period']


def test_fujian_application_required_stops_before_fetching_rows():
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(200,json={'code':200,'data':{'openType':'0'}})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValueError,match='依申请开放'):
            fetch_local(client,'fujian/'+('A'*32))
    assert len(calls)==1


def test_fujian_search_rejects_foreign_url_in_catalog_id():
    def respond(request):
        return httpx.Response(200,json={'code':200,'data':{'rows':[{'catalogID':'https://evil.example','catalogName':'人口','openType':'1'}]}})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValueError,match='未找到匹配'):
            fetch_local(client,'fujian/search:人口')


@pytest.mark.parametrize('region',list(FUJIAN_CITIES))
def test_fujian_city_filter_and_provenance(region):
    def respond(request):
        path=request.url.path
        if path.endswith('/list'):
            assert request.url.params['cityCode']==FUJIAN_CITIES[region][1]
            assert request.url.params['currentTab']=='city'
            data={'rows':[{'catalogID':'A'*32,'catalogName':'生产总值','openType':'1'}]}
        elif path.endswith('/getCataInfo'):
            data={'catalogName':'生产总值','openType':'1','dataVol':1}
        elif path.endswith('/getCataItem'):
            data=[{'nameEn':'gdp','nameCn':'生产总值'}]
        else:data={'rows':[{'gdp':100}],'total':1}
        return httpx.Response(200,json={'code':200,'data':data})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result=fetch_local(client,region+'/search:生产总值')
        with pytest.raises(ValueError):fetch_local(client,region+'/'+('A'*32))
    assert result['facts']['region']==region
    assert result['facts']['selection']['city_filter']['code']==FUJIAN_CITIES[region][1]


def test_biometric_columns_are_rejected_before_reading_values():
    def respond(request):
        if request.url.path.endswith('/getCataInfo'):data={'openType':'1'}
        else:
            assert request.url.path.endswith('/getCataItem')
            data=[{'nameEn':'face','nameCn':'人脸特征值'}]
        return httpx.Response(200,json={'code':200,'data':data})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValueError,match='个人明细'):fetch_local(client,'fujian/'+('A'*32))
