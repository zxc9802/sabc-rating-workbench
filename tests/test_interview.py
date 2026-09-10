from tests.test_app import client
from tests.test_rating import case
import pytest


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


@pytest.mark.parametrize('reply,expected',[
    ('预算已记下。你打算先解决哪类问题？怎样才算成功？',
     '预算已记下。你打算先解决哪类问题？怎样才算成功？'),
    ('预算已记下。','预算已记下。\n\n准备解决什么问题？\n\n如何判断成功？'),
])
def test_questions_are_visible_once_and_waiting_state_matches_interview(client,monkeypatch,reply,expected):
    import sabc.app as module
    pid=client.post('/api/projects',json={'name':'多轮测试','project_type':'growth'}).json()['id']
    monkeypatch.setattr(module,'settings',lambda:{'base_url':'https://model.example','model':'test'})
    monkeypatch.setattr(module.planner,'configured',lambda:False)
    monkeypatch.setattr(module,'analyze',lambda *args:{
        'mode':'model','reply':reply,'project_patch':{},'proposal':None,
        'questions':['准备解决什么问题？','如何判断成功？'],'needs_external_action':True})
    response=client.post(f'/api/projects/{pid}/chat',json={'message':'预算已确定，服务方向不知道'})
    assert response.json()['reply']==expected
    project=client.get(f'/api/projects/{pid}').json()['project']
    assert project['messages'][-1]['content']==expected
    assert project['interview']['state']=='gathering'
