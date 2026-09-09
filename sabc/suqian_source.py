"""Read official Suqian statistical articles found in its public data listing."""
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

LISTING = 'https://data.suqian.gov.cn/sjkfpt.shtml'


def fetch_article(client, keyword):
    from sabc.local_sources import public_request

    response = public_request(client, 'get', LISTING)
    soup = BeautifulSoup(response.content, 'html.parser')
    selected = None
    for link in soup.select('a[href]'):
        title = link.get_text(' ', strip=True)
        url = urljoin(LISTING, link['href'])
        parsed = urlparse(url)
        if (parsed.scheme in ('http', 'https') and parsed.netloc == 'www.suqian.gov.cn'
                and re.fullmatch(r'/cnsq/sjdt/\d{6}/[a-f0-9]{32}\.shtml', parsed.path)
                and all(word in title for word in keyword.split())):
            selected = (title, url)
            break
    if selected is None:
        raise ValueError('宿迁当前公开列表没有匹配统计文章；不使用其他地区替代')
    title, url = selected
    response = public_request(client, 'get', url)
    article = BeautifulSoup(response.content, 'html.parser').select_one('#zoomcon')
    if article is None:
        raise ValueError('宿迁统计文章正文结构已变化，未保存证据')
    text = article.get_text('\n', strip=True)
    if len(text) < 30 or not re.search(r'\d+(?:\.\d+)?', text):
        raise ValueError('宿迁文章未取得有效统计正文，未保存证据')
    return dict(title=title, period=title + '；具体月度或累计区间见正文',
                facts={'region': 'suqian', 'text': text,
                       'selection': {'keyword': keyword, 'listing': LISTING,
                                     'method': '当前公开列表首篇标题匹配统计文章'}},
                limitation='宿迁市公开统计正文，不代表江苏全省；单位与累计期间以原文为准，不可将累计数据相加，不证明项目需求或利润。列表非完整历史检索。',
                locator=url, response=response)
