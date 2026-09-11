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
    assert second['interview']['state']=='gathering'
    assert second['proposal'] is None
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


def test_no_followup_keeps_incomplete_interview_paused(client,monkeypatch):
    import sabc.app as module
    pid=client.post('/api/projects',json={'name':'未知保留','project_type':'growth'}).json()['id']
    monkeypatch.setattr(module,'settings',lambda:{'base_url':'https://model.example','model':'test'})
    monkeypatch.setattr(module.planner,'configured',lambda:False)
    monkeypatch.setattr(module,'analyze',lambda *args:{
        'mode':'model','reply':'已修正资料，具体需求仍需验证。','project_patch':{},
        'proposal':None,'questions':[],'needs_external_action':False})
    client.post(f'/api/projects/{pid}/chat',json={'message':'请保留尚未核实的信息'})
    project=client.get(f'/api/projects/{pid}').json()['project']
    assert project['interview']['state']=='paused'
    assert project['interview']['gaps'] and not project['interview']['questions']


@pytest.mark.parametrize('outcome', ['rated', 'unknown', 'ask', 'pending'])
def test_collection_completion_waits_for_explicit_report_action(client, monkeypatch, outcome):
    from copy import deepcopy
    import sabc.app as module
    p, company, _, proposal = case()
    client.put('/api/company', json=company)
    pid = client.post('/api/projects', json=p).json()['id']
    project = module.store.get('projects', pid)
    project['lifecycle'] = {**module.lifecycle.initial(), 'stage': 'pre', 'confirmed': True, 'coverage': {
        key: {'status': 'external' if key == 'risk' else 'known', 'reason': '已梳理，监管适用留待外部核查'}
        for key in module.DIMENSIONS}, 'reviews': []}
    module.store.save('projects', project)
    monkeypatch.setattr(module, 'settings', lambda: {'base_url': 'https://model.example', 'model': 'test'})
    requests = []
    def reply(settings, key, project, *args):
        requests.append(project['_report_requested'])
        coverage = deepcopy(project['lifecycle']['coverage'])
        assessment_proposal = deepcopy(proposal)
        questions = []
        patch = {}
        if project['_prepare_report']:
            if outcome == 'unknown':
                coverage['market'] = {'status': 'unknown', 'reason': '用户明确无法提供需求信息'}
                assessment_proposal['dimensions']['market'].update(score=None, basis='unknown')
            elif outcome == 'ask':
                coverage['market'] = {'status': 'ask', 'reason': '尚可回答的目标客户问题'}
                questions = ['目标客户是谁？']
            elif outcome == 'pending':
                patch = {'risks': '新补充的风险需要确认'}
        return {'mode': 'model', 'reply': '本阶段信息已梳理完整', 'questions': questions, 'project_patch': patch,
                'dimension_coverage': coverage, 'proposal': assessment_proposal,
                'stage_review': {'conclusion': 'trial', 'summary': '阶段初评', 'next_action': '验证', 'next_review_days': 14}}
    monkeypatch.setattr(module, 'analyze', reply)
    url = f'/api/projects/{pid}'
    ordinary = client.post(url + '/chat', json={'message': '资料补充完了'})
    assert ordinary.status_code == 200
    detail = client.get(url).json()
    assert detail['assessments'] == []
    assert not ordinary.json().get('report_id')
    assert detail['project']['report_ready'] == (outcome != 'ask')
    requested = client.post(url + '/chat', json={'message': '生成报告', 'generate_report': True})
    assert requested.status_code == 200
    assert requests == [False]  # Click never calls analysis or review.
    reports = client.get(url).json()['assessments']
    if outcome == 'ask':
        assert reports == []
        assert requested.json().get('needs_collection')
    else:
        assert len(reports) == 1
        assert reports[0]['id'] == requested.json()['report_id']
        assert reports[0]['result']['grade'] == ('NR' if outcome == 'unknown' else 'B')
        if outcome == 'unknown':
            assert '用户明确无法提供需求信息' in reports[0]['result']['deferral_reason']
    project = module.store.get('projects', pid)
    project['lifecycle']['coverage']['risk']['status'] = 'ask'
    module.store.save('projects', project)
    assert client.post(url + '/chat', json={'message':'生成报告','generate_report':True}).json()['needs_collection']
    assert requests == [False]


def test_continuous_interview_uses_latest_report_across_legacy_stages(client, monkeypatch):
    import sabc.app as module
    p, c, _, _ = case()
    client.put('/api/company', json=c)
    project = client.post('/api/projects', json=p).json()
    assert project['lifecycle']['mode'] == 'continuous'
    pid = project['id']
    for stage in ('pre', 'post'):
        module.store.save('assessments', {
            'id': stage + '-saved', 'project_id': pid, 'result': {'stage': stage},
            'snapshot': {'project': {'lifecycle': module.lifecycle.initial(stage)}}})
    project['lifecycle']['previous_report_id'] = 'pre-saved'
    project['lifecycle']['confirmed'] = False  # An old record must not need a stage selector.
    module.store.save('projects', project)
    seen = []
    def reply(settings, key, current, *args):
        seen.append(current)
        return {'mode': 'model', 'reply': '实际执行后成本有什么变化？',
                'questions': ['实际执行后成本有什么变化？'], 'project_patch': {}, 'proposal': None,
                'dimension_coverage': {key: {'status': 'ask', 'reason': '核对本次新情况'} for key in module.DIMENSIONS}}
    monkeypatch.setattr(module, 'settings', lambda: {'base_url': 'https://model.example', 'model': 'test'})
    monkeypatch.setattr(module, 'analyze', reply)
    response = client.post(f'/api/projects/{pid}/chat', json={'message': '继续评估'})
    assert response.status_code == 200
    assert seen[0]['_previous_stage_report']['id'] == 'post-saved'
    detail = client.get(f'/api/projects/{pid}').json()
    assert len(detail['assessments']) == 2
    assert detail['project']['lifecycle']['confirmed'] is True
    assert detail['project']['messages'][-1]['content'] == '实际执行后成本有什么变化？'
