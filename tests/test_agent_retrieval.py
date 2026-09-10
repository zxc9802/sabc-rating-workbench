from tests.test_app import client
import sabc.app as module


def test_dedicated_planner_runs_before_collect_and_analysis(client,monkeypatch):
    monkeypatch.setattr(module,'settings',lambda:{'base_url':'https://model.example','model':'test'})
    monkeypatch.setattr(module.planner,'configured',lambda:True)
    calls=[]
    def plan(*args):
        calls.append('plan')
        return {'reason':'核验依赖','data_requests':[{'source':'github','query':'a/b','reason':'技术'}]}
    def collect(store,pid,source,query):
        calls.append('collect')
        return store.save('evidence',{'project_id':pid,'content':'公开事实'})
    def analyze(*args):
        calls.append('analyze')
        assert len(args[4])==1
        return {'mode':'model','reply':'分析结果','project_patch':{},'proposal':None}
    monkeypatch.setattr(module.planner,'plan_search',plan)
    monkeypatch.setattr(module,'collect',collect)
    monkeypatch.setattr(module,'analyze',analyze)
    pid=client.post('/api/projects',json={'name':'测试'}).json()['id']
    result=client.post(f'/api/projects/{pid}/chat',json={'message':'检查'}).json()
    assert calls==['plan','collect','analyze']
    assert result['retrieval_plan']['status']=='planned'
    assert len(module.store.list('retrieval_plans'))==1


def test_planner_failure_is_explicit_and_does_not_trigger_collection(client,monkeypatch):
    monkeypatch.setattr(module,'settings',lambda:{'base_url':'https://model.example','model':'test'})
    monkeypatch.setattr(module.planner,'configured',lambda:True)
    def fail(*args): raise ValueError('选源模型请求失败（HTTP 503）')
    monkeypatch.setattr(module.planner,'plan_search',fail)
    def collect(*args): raise AssertionError('must not collect after failed planning')
    monkeypatch.setattr(module,'collect',collect)
    monkeypatch.setattr(module,'analyze',lambda *args:{'mode':'model','reply':'请补充资料','project_patch':{},'proposal':None})
    pid=client.post('/api/projects',json={'name':'测试'}).json()['id']
    result=client.post(f'/api/projects/{pid}/chat',json={'message':'检查'}).json()
    assert result['retrieval_plan']['status']=='skipped'
    assert '503' not in result['reply']
    assert module.store.list('retrieval_plans')[0]['status']=='failed'


def test_selected_evidence_is_passed_back_once(client,monkeypatch):
    monkeypatch.setattr(module.planner,"plan_search",lambda *a:{"data_requests":[{"source":"github","query":"a/b","reason":"技术"}]})
    monkeypatch.setattr(module,'settings',lambda:{'base_url':'https://model.example','model':'test'})
    calls=[]
    def analyze(*args):
        calls.append(args)
        return {'mode':'model','reply':'结果','project_patch':{},'proposal':None,'data_requests':[{'source':'github','query':'a/b','reason':'核对技术依赖'}]}
    monkeypatch.setattr(module,'analyze',analyze)
    def collect(store,pid,source,query):
        return store.save('evidence',{'project_id':pid,'source_id':source,'query':query,'retrieved_at':module.utcnow(),'content':'真实调用在单独验收脚本验证'})
    monkeypatch.setattr(module,'collect',collect)
    pid=client.post('/api/projects',json={'name':'测试'}).json()['id']
    r=client.post(f'/api/projects/{pid}/chat',json={'message':'检查技术依赖'}).json()
    assert len(calls)==1 and len(calls[0][4])==1
    assert r['retrieval_results'][0]['status']=='saved'
    r=client.post(f'/api/projects/{pid}/chat',json={'message':'继续'}).json()
    assert r['retrieval_results'][0]['status']=='saved'
    assert len(client.get(f'/api/projects/{pid}').json()['evidence'])==2
    assert len(calls)==2


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


def test_retrieval_failure_still_returns_interview(client,monkeypatch):
    monkeypatch.setattr(module.planner,"plan_search",lambda *a:{"data_requests":[{"source":"github","query":"a/b","reason":"技术"}]})
    monkeypatch.setattr(module,'settings',lambda:{'base_url':'https://model.example','model':'test'})
    monkeypatch.setattr(module,'analyze',lambda *args:{'mode':'model','reply':'待核验','project_patch':{},'proposal':None,'data_requests':[{'source':'github','query':'a/b','reason':'技术'}]})
    def fail(*args): raise ValueError('HTTP 403')
    monkeypatch.setattr(module,'collect',fail)
    pid=client.post('/api/projects',json={'name':'测试'}).json()['id']
    r=client.post(f'/api/projects/{pid}/chat',json={'message':'检查'}).json()
    assert r['retrieval_results']==[]
    assert '403' not in r['reply'] and '暂缓' not in r['reply']
    assert module.store.list('source_runs')[0]['error']=='HTTP 403'


def test_one_failed_source_does_not_block_second_or_leak_error(client,monkeypatch):
    monkeypatch.setattr(module,'settings',lambda:{'base_url':'https://model.example','model':'test'})
    monkeypatch.setattr(module.planner,'configured',lambda:True)
    monkeypatch.setattr(module.planner,'plan_search',lambda *a:{'reason':'核对公开资料','data_requests':[
        {'source':'github','query':'a/b','reason':'技术'}, {'source':'web','query':'公开文档','reason':'文档'}]})
    def collect(store,pid,source,query):
        if source=='github':raise RuntimeError('upstream private diagnostic 503')
        return store.save('evidence',{'project_id':pid,'content':'可用公开文档'})
    def analyze(*args):
        assert len(args[4])==1
        assert 'private diagnostic' not in str(args[5])
        return {'mode':'model','reply':'根据已有资料继续判断','project_patch':{},'proposal':None}
    monkeypatch.setattr(module,'collect',collect)
    monkeypatch.setattr(module,'analyze',analyze)
    pid=client.post('/api/projects',json={'name':'混合渠道测试'}).json()['id']
    r=client.post(f'/api/projects/{pid}/chat',json={'message':'查询'}).json()
    assert len(r['retrieval_results'])==1 and r['retrieval_results'][0]['source']=='web'
    assert '503' not in r['reply']
