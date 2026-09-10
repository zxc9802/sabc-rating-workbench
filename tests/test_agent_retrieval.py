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
    result=client.post(f'/api/projects/{pid}/chat',json={'message':'核查依赖'}).json()
    assert calls==[0,1]
    assert result['retrieval_results'][0]['status']=='saved'
    result=client.post(f'/api/projects/{pid}/chat',json={'message':'继续'}).json()
    assert calls==[0,1,1]
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
    result=client.post(f'/api/projects/{pid}/chat',json={'message':'核查'}).json()
    assert result['retrieval_results'][0]['status']=='failed'
    assert 'failed' in seen[1][-1]['content']
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
    client.post(f'/api/projects/{pid}/chat',json={'message':'继续'})
    assert len(seen)==1 and seen[0]['content']=='接口历史记录'
