import time
import httpx
import pytest
from sabc import planner, vector_sources


def select(monkeypatch, source, **extra):
    monkeypatch.setattr(vector_sources,'rank',lambda text:[{'id':source,'source':source,'similarity':.8,**extra},{'id':'none','source':'none','similarity':.2}])


def plan(text, project=None, evidence=None):
    return planner.plan_search(project or {}, {}, evidence or [],[{'role':'user','content':text}])


@pytest.mark.parametrize('source,text,query',[
    ('github','核查github.com/fastapi/fastapi的维护情况','fastapi/fastapi'),
    ('worldbank','查询越南人口规模','VN/SP.POP.TOTL'),
    ('sec','请查CIK 320193的财报','320193/facts'),
    ('law','中国客服把客户聊天记录发给外部模型','个人信息保护'),
    ('trends','美国热门搜索','US'),
    ('apple','App商店查询 us/notion','us/notion'),
    ('stats','读取 https://www.stats.gov.cn/sj/example.html','https://www.stats.gov.cn/sj/example.html'),
])
def test_queries_are_grounded(monkeypatch,source,text,query):
    select(monkeypatch,source)
    assert plan(text)['data_requests'][0]['query']==query


@pytest.mark.parametrize('source,text',[
    ('github','核查这个开源项目'),('sec','查某公司的财报'),
    ('stats','查询最新国家统计数字'),('worldbank','查询人口'),
    ('law','越南项目，上海团队负责，核查隐私法律'),
    ('law','客户聊天记录发给外部模型，国家还没定'),
    ('trends','查询越南防晒历史搜索指数'),
    ('cninfo','下载 https://evil.example/report.pdf'),
])
def test_missing_or_inapplicable_parameters_are_not_invented(monkeypatch,source,text):
    select(monkeypatch,source)
    assert plan(text)['data_requests']==[]


def test_region_is_not_replaced_by_similar_region(monkeypatch):
    select(monkeypatch,'local',region='suqian')
    assert plan('查询阿克苏人口')['data_requests']==[]
    assert plan('查询宿迁商务统计')['data_requests'][0]['query']=='suqian/search:商务统计'


def test_none_candidate_prevents_irrelevant_search(monkeypatch):
    monkeypatch.setattr(vector_sources,'rank',lambda t:[{'id':'none','source':'none','similarity':.6},{'id':'law','source':'law','similarity':.3}])
    assert plan('预算8000元，两名客服参加')['data_requests']==[]


def test_private_text_never_goes_to_web_query(monkeypatch):
    monkeypatch.setenv('ANYSEARCH_API_KEY','test')
    select(monkeypatch,'web')
    assert plan('查询内部客户名单13812345678')['data_requests']==[]


def test_existing_results_and_unconfigured_sources(monkeypatch):
    select(monkeypatch,'github')
    evidence=[{'source_id':'github','query':'fastapi/fastapi','retrieved_at':time.strftime('%Y-%m-%d')}]
    assert plan('核查 fastapi/fastapi',evidence=evidence)['data_requests']==[]
    assert plan('重新查 fastapi/fastapi',evidence=evidence)['data_requests']
    select(monkeypatch,'web')
    monkeypatch.delenv('ANYSEARCH_API_KEY',raising=False)
    assert plan('查询越南防晒法规')['data_requests']==[]


def test_failure_does_not_fallback_to_chat_model(monkeypatch):
    def fail(text):raise ValueError('向量接口不可用')
    monkeypatch.setattr(vector_sources,'rank',fail)
    monkeypatch.setattr(httpx.Client,'post',lambda *a,**kw:pytest.fail('不得调用聊天模型'))
    with pytest.raises(ValueError):plan('查询越南人口')


def test_embedding_response_order_and_finite_values(monkeypatch):
    monkeypatch.setenv('SABC_EMBEDDING_API_KEY','test')
    rows=[{'index':1,'embedding':[0,1]},{'index':0,'embedding':[1,0]}]
    def post(self,url,**kw):
        assert url.endswith('/embeddings')
        return httpx.Response(200,request=httpx.Request('POST',url),json={'data':rows})
    monkeypatch.setattr(httpx.Client,'post',post)
    assert vector_sources.embed(['a','b'])==[[1,0],[0,1]]
    rows[0]['embedding']=[0,0]
    with pytest.raises(ValueError):vector_sources.embed(['a','b'])


def test_bundled_index_matches_capabilities_and_model(monkeypatch):
    import gzip,json
    with gzip.open(vector_sources.INDEX,'rt') as f:data=json.load(f)
    assert data['fingerprint']==vector_sources.fingerprint(vector_sources.capabilities(),data['model'])
    monkeypatch.setenv('SABC_EMBEDDING_MODEL','wrong-model')
    with pytest.raises(ValueError,match='重新生成'):vector_sources.rank('test')
