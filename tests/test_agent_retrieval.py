from tests.test_app import client
import sabc.app as module
from sabc.dimension_sources import plan_requests


def test_dimension_routing_collects_then_analyzes_and_reuses(client,monkeypatch):
    monkeypatch.setattr(module,'settings',lambda:{'base_url':'https://model.example','model':'test'})
    calls=[]
    def analyze(*args):
        calls.append(len(args[4]))
        return {'mode':'model','reply':'核查结果','project_patch':{},'proposal':None,'data_requests':[{'dimension':'resources','source':'github','query':'a/b','reason':'依赖维护'}]}
    def collect(store,pid,source,query):
        return store.save('evidence',{'project_id':pid,'source_id':source,'query':query,'retrieved_at':module.utcnow(),'content':'公开资料'})
    monkeypatch.setattr(module,'analyze',analyze)
    monkeypatch.setattr(module,'collect',collect)
    pid=client.post('/api/projects',json={'name':'测试'}).json()['id']
    result=client.post(f'/api/projects/{pid}/chat',json={'message':'核查开源依赖 https://github.com/a/b'}).json()
    assert calls==[1]
    assert result['retrieval_results'][0]['status']=='saved'
    result=client.post(f'/api/projects/{pid}/chat',json={'message':'继续核查开源依赖'}).json()
    assert calls==[1,1]
    assert result['retrieval_plan']['candidates'][0]['status']=='existing_evidence'
    assert len(client.get(f'/api/projects/{pid}').json()['evidence'])==1


def test_failed_collection_is_passed_to_answer_model(client,monkeypatch):
    monkeypatch.setattr(module,'settings',lambda:{'base_url':'https://model.example','model':'test'})
    seen=[]
    def analyze(*args):
        seen.append(args[-1])
        return {'mode':'model','reply':'外部事实尚未核查','project_patch':{},'proposal':None,'data_requests':[{'dimension':'resources','source':'github','query':'a/b','reason':'依赖'}]}
    def fail(*args): raise ValueError('upstream unavailable')
    monkeypatch.setattr(module,'analyze',analyze)
    monkeypatch.setattr(module,'collect',fail)
    pid=client.post('/api/projects',json={'name':'测试'}).json()['id']
    result=client.post(f'/api/projects/{pid}/chat',json={'message':'核查开源依赖 https://github.com/a/b'}).json()
    assert result['retrieval_results'][0]['status']=='failed'
    assert 'failed' in seen[0][-1]['content']
    assert len(module.store.list('source_runs'))==1


def test_rules_reject_wrong_dimension_and_invalid_parameters():
    result=plan_requests([{'dimension':'cash','source':'github','query':'a/b'}, {'dimension':'resources','source':'github','query':'猜一个仓库'}],[],'')
    assert not result['data_requests']
    assert [r['status'] for r in result['candidates']]==['dimension_not_allowed','invalid_parameters']


def test_public_query_does_not_require_user_search_keyword(monkeypatch):
    monkeypatch.setenv('ANYSEARCH_API_KEY','test')
    result=plan_requests([{'dimension':'risk','source':'web','query':'Indonesia BPOM sunscreen registration official requirements','reason':'准入条件需核查'}],[],'先做样品测试')
    assert len(result['data_requests'])==1


def test_internal_information_does_not_force_lookup():
    assert not plan_requests([],[],'预算8000元')['data_requests']


def test_unsupported_or_sensitive_query_is_not_executed(monkeypatch):
    monkeypatch.setenv('ANYSEARCH_API_KEY','test')
    result=plan_requests([{'dimension':'market','source':'baidu','query':'防晒'}, {'dimension':'market','source':'web','query':'客户名单 手机号'}],[],'')
    assert not result['data_requests']


def test_browser_captures_excluded_from_model_context(client,monkeypatch):
    monkeypatch.setattr(module,'settings',lambda:{'base_url':'https://model.example','model':'test'})
    seen=[]
    def analyze(*args):
        seen.extend(args[4])
        return {'mode':'model','reply':'请补充地区','project_patch':{},'proposal':None,'data_requests':[]}
    monkeypatch.setattr(module,'analyze',analyze)
    pid=client.post('/api/projects',json={'name':'测试'}).json()['id']
    module.store.save('evidence',{'project_id':pid,'capture_method':'browser-observation','content':'过期屏幕资料'})
    module.store.save('evidence',{'project_id':pid,'source_id':'local','content':'接口历史记录'})
    client.post(f'/api/projects/{pid}/chat',json={'message':'继续核查开源依赖'})
    assert len(seen)==1 and seen[0]['content']=='接口历史记录'


def test_retrieval_draft_is_not_shown_before_final_answer(client, monkeypatch):
    from sabc.streaming import progress
    monkeypatch.setattr(module, 'settings', lambda: {'base_url': 'https://model.example', 'model': 'test'})
    calls = []
    visible = []
    def analyze(*args):
        calls.append(1)
        reply = '依据资料的最终回答'
        notify = progress.get()
        if notify:
            notify('')
            notify(reply)
        return {'mode': 'model', 'reply': reply, 'project_patch': {}, 'proposal': None,
                'data_requests': [{'dimension': 'resources', 'source': 'github', 'query': 'a/b', 'reason': '依赖'}]}
    monkeypatch.setattr(module, 'analyze', analyze)
    monkeypatch.setattr(module, 'collect', lambda *args: {'id': 'evidence'})
    pid = client.post('/api/projects', json={'name': '测试'}).json()['id']
    token = progress.set(visible.append)
    try:
        client.post(f'/api/projects/{pid}/chat', json={'message': '核查开源依赖 https://github.com/a/b'})
    finally:
        progress.reset(token)
    assert '依据资料的最终回答' in visible
    assert '正在选择数据源的草稿' not in visible
    assert len(calls) == 1


def test_rules_trigger_without_model_request_and_keep_region(monkeypatch):
    from sabc.dimension_sources import rule_plan
    monkeypatch.setenv('ANYSEARCH_API_KEY', 'test')
    plan = rule_plan({'description': '我想做印尼防晒项目'}, '开始', [])
    assert {r['dimension'] for r in plan['data_requests']} == {'market', 'risk'}
    assert all(r['source'] == 'web' and '印尼' in r['query'] for r in plan['data_requests'])
    assert not rule_plan({'description': '预算8000元'}, '人员2人', [])['data_requests']
    missing = rule_plan({'description': '想做防晒'}, '合规怎么样', [])
    assert not missing['data_requests'] and missing['missing_parameters']
    china = rule_plan({'description': '中国防晒'}, '合规', [])
    assert any(r['source'] == 'law' for r in china['data_requests'])


def test_rule_collection_is_parallel_and_precedes_only_answer(client, monkeypatch):
    from threading import Barrier
    monkeypatch.setenv('ANYSEARCH_API_KEY', 'test')
    monkeypatch.setattr(module, 'settings', lambda: {'base_url': 'https://model.example', 'model': 'test'})
    barrier = Barrier(2)
    collected = []
    def collect(*args):
        barrier.wait(timeout=2)
        collected.append(args[-1])
        return {'id': args[-1]}
    def analyze(*args):
        assert len(collected) == 2
        return {'mode': 'model', 'reply': '结果', 'project_patch': {}, 'proposal': None, 'data_requests': []}
    monkeypatch.setattr(module, 'collect', collect)
    monkeypatch.setattr(module, 'analyze', analyze)
    pid = client.post('/api/projects', json={'name': '测试', 'description': '印尼防晒项目'}).json()['id']
    result = client.post(f'/api/projects/{pid}/chat', json={'message': '市场和合规'}).json()
    assert len(result['retrieval_results']) == 2
    assert all(r['status'] == 'saved' for r in result['retrieval_results'])
def test_business_outsourcing_is_not_a_missing_github_dependency():
    from sabc.dimension_sources import rule_plan
    project = {'description': '泰国防晒OEM', 'lifecycle': {'coverage': {'resources': {'status': 'external'}}}}
    plan = rule_plan(project, '外包依赖是泰语客服和合规代理，均未落实，报价未知', [])
    assert not any(x['dimension'] == 'resources' for x in plan['missing_parameters'])
    software = rule_plan(project, '需要核查开源依赖但仓库地址没提供', [])
    assert any(x['dimension'] == 'resources' for x in software['missing_parameters'])
