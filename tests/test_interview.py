from tests.test_app import client
from tests.test_rating import case


def test_pending_facts_merge_and_readiness_uses_rule_engine(client,monkeypatch):
    import sabc.app as module
    p,c,_,proposal=case()
    client.put('/api/company',json=c)
    pid=client.post('/api/projects',json=p).json()['id']
    monkeypatch.setattr(module,'settings',lambda:{'base_url':'https://model.example','model':'test'})
    monkeypatch.setattr(module.planner,'configured',lambda:False)
    replies=iter([{'mode':'model','reply':'补充','project_patch':{'risks':'早先待确认风险'},'proposal':None,'needs_external_action':True},
                  {'mode':'model','reply':'资料齐备','project_patch':{'timeframe':'4周'},'proposal':proposal,'questions':['不应继续追问']}])
    monkeypatch.setattr(module,'analyze',lambda *args:next(replies))
    client.post(f'/api/projects/{pid}/chat',json={'message':'第一轮'})
    first=client.get(f'/api/projects/{pid}').json()['project']
    assert first['interview']['state']=='paused'
    client.post(f'/api/projects/{pid}/chat',json={'message':'第二轮'})
    second=client.get(f'/api/projects/{pid}').json()['project']
    assert second['pending_patch']=={'risks':'早先待确认风险','timeframe':'4周'}
    assert second['risks']==p['risks']
    assert second['interview']['state']=='ready' and second['interview']['questions']==[]
    assert client.post(f'/api/projects/{pid}/assess',json={'confirmed':True}).status_code==422
