"""Public capability embeddings, built offline; user queries are never persisted here."""
import gzip
import hashlib
import json
import math
import os
from pathlib import Path

import httpx

from sabc.catalog import catalog
from sabc.local_sources import REGIONS

INDEX = Path(__file__).with_name('source_vectors.json.gz')


def config():
    return {'model': os.getenv('SABC_EMBEDDING_MODEL', 'text-embedding-3-large'),
            'base_url': os.getenv('SABC_EMBEDDING_BASE_URL') or os.getenv('SABC_PLANNER_BASE_URL', 'https://api.openlux.ai/v1'),
            'key': os.getenv('SABC_EMBEDDING_API_KEY') or os.getenv('SABC_PLANNER_API_KEY', '')}


def capabilities():
    details = {
        'web': '搜索最新公开信息、海外市场和行业资料、产品准入规定。需要公开搜索词。不能查询本公司内部预算、客户资料或用市场资料证明项目利润。',
        'stats': '读取国家统计局已知官方文章网址的正文，不能直接按关键词搜索。宏观统计不是项目需求。',
        'miit': '读取工信部已知官方文章网址的产业统计正文，必须提供具体网址。',
        'cninfo': '读取巨潮资讯已知官方公告PDF，须有完整网址；不能按公司名称搜索财报。',
        'law': '中国国家法律法规库关键词检索，查经营边界、个人信息处理、数据安全、广告宣传、知识产权、劳动用工。需核对适用地区和原文，不能据此直接判定项目违法。',
        'worldbank': '国家人口、GDP宏观统计。需要国家代码和指标代码，不能证明项目客户数量或收入。',
        'github': '核查公开开源软件仓库活跃度、许可证、维护情况。必须有owner/repository，不能猜测仓库名称。',
        'sec': '美国上市公司披露与财务数据，需要用户提供CIK公司编号，不能猜编号。',
        'apple': 'App Store应用竞品检索、价格、评分。需要商店国家和应用关键词，不能推算销量和收入。',
        'trends': 'Google热门搜索RSS，需要国家代码；不能查指定关键词的历史搜索指数。',
        'local': '地方公开统计与目录，按项目所在地匹配，不能用异地统计代替目标地区。',
    }
    cards = [dict(id=s['id'], source=s['id'], text=f"{s['name']}：{s['purpose']}。{s['access']}。{details.get(s['id'], '尚不支持自动取数。')}") for s in catalog()]
    cards += [dict(id='local:'+r['id'], source='local', region=r['id'],
                   text=f"查询{r['name']}公开统计数据：{r['method']}。{r['note']}。参数示例：{r.get('example', '暂无自动接口')}") for r in REGIONS]
    cards += [dict(id='web:overseas', source='web', text='查询海外产品市场准入规定、化妆品防晒等商品的注册要求，搜索目标国家官方公开政策。需要明确国家、产品和公开问题，不使用中国法规代替外国规定。'),
              dict(id='worldbank:population', source='worldbank', text='查询一个国家的人口规模、人口数量、人口总数，例如越南、泰国、美国。世界银行国家人口统计。必须明确国家；不代表产品需求。'),
              dict(id='worldbank:gdp', source='worldbank', text='查询某个国家的GDP、国内生产总值。世界银行宏观经济统计，必须明确国家，不能代表本项目收入。')]
    cards += [dict(id='none:'+str(i), source='none', text=t) for i,t in enumerate([
        '补充公司内部预算、人员安排、试点周期、工时、实际成本和目标；这些是用户提供的内部事实，无需外部数据。',
        '解释之前的问题，整理已有材料，继续访谈，生成试点计划；已有信息足够，不需要再查公开资料。',
        '想做一个项目，先讨论具体需求和痛点，还没有明确需要核验的外部问题。',
    ])]
    return cards


def fingerprint(cards, model):
    return hashlib.sha256(json.dumps([model, cards], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def embed(texts):
    c = config()
    if not c['key'] or not c['base_url'].startswith('https://'):
        raise ValueError('向量模型未配置有效的HTTPS地址和密钥')
    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(c['base_url'].rstrip('/')+'/embeddings',
                            headers={'Authorization':'Bearer '+c['key']},
                            json={'model':c['model'], 'input':texts})
            r.raise_for_status()
            rows = sorted(r.json()['data'], key=lambda x:x['index'])
        if [r['index'] for r in rows] != list(range(len(texts))):
            raise ValueError()
        vectors = [r['embedding'] for r in rows]
        size = len(vectors[0])
        if not size or any(len(v)!=size or any(not isinstance(x,(float,int)) or isinstance(x,bool) or not math.isfinite(x) for x in v) or not sum(x*x for x in v) for v in vectors):
            raise ValueError()
        return vectors
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
        raise ValueError('向量接口未返回有效结果，本轮保留外部核查缺口') from None


def build_index(path=INDEX):
    cards = capabilities()
    vectors = embed([c['text'] for c in cards])
    data = {'model':config()['model'], 'fingerprint':fingerprint(cards, config()['model']),
            'cards':cards, 'vectors':vectors}
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    with gzip.open(temporary, 'wt', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    temporary.replace(path)
    return {'cards':len(cards), 'dimensions':len(vectors[0]), 'fingerprint':data['fingerprint']}


def rank(text):
    cards = capabilities()
    with gzip.open(INDEX, 'rt', encoding='utf-8') as f:
        data = json.load(f)
    if data['fingerprint'] != fingerprint(cards, config()['model']):
        raise ValueError('接口能力或向量模型已变更，需要重新生成能力索引')
    query = embed([text])[0]
    norm = math.sqrt(sum(x*x for x in query))
    ranked = []
    for card, vector in zip(cards, data['vectors'], strict=True):
        if len(vector)!=len(query):
            raise ValueError('向量维度与能力索引不一致')
        score = sum(x*y for x,y in zip(query,vector))/(norm*math.sqrt(sum(x*x for x in vector)))
        ranked.append({**card, 'similarity':score})
    return sorted(ranked, key=lambda c:c['similarity'], reverse=True)


if __name__ == '__main__':
    print(json.dumps(build_index(), ensure_ascii=False))
