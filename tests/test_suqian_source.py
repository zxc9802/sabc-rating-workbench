import httpx
import pytest

from sabc.local_sources import fetch_local

PATH = '/cnsq/sjdt/202608/' + 'a' * 32 + '.shtml'


def test_public_article_preserves_units_and_cumulative_wording():
    def handler(request):
        if request.url.host == 'data.suqian.gov.cn':
            return httpx.Response(200, text=f'<a href="https://www.suqian.gov.cn{PATH}">2026年6月商务统计数据</a>')
        return httpx.Response(200, text='<div id="zoomcon">1-6月份，全市实现货物进出口42.15亿美元；全市实现社零总额930.3亿元，同比增长2.6%。</div>')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result=fetch_local(client,'suqian/search:商务统计')
    assert '1-6月份' in result['facts']['text']
    assert '亿美元' in result['facts']['text']
    assert result['facts']['region']=='suqian'
    assert '不代表江苏全省' in result['limitation']


@pytest.mark.parametrize('link', ['https://example.com'+PATH,
                                 'https://www.suqian.gov.cn/login',
                                 'https://www.suqian.gov.cn.evil.example'+PATH])
def test_foreign_or_nonstatistical_links_are_not_followed(link):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,text=f'<a href="{link}">商务统计</a>')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError,match='没有匹配统计文章'):
            fetch_local(client,'suqian/search:商务统计')
    assert len(calls)==1
