from copy import deepcopy
from datetime import date
import pytest
from sabc import lifecycle as lc
from sabc.rating import DIMENSIONS, assess
from sabc.context import model_context
from tests.test_rating import case
from tests.test_app import client


def plan():
    return {'objective':'验证客服净提效','scope':'2名客服，三类工单','method':'相同口径对照并抽查质量',
            'metrics':[{'name':'净释放工时','baseline':'每单10分钟','target':'每月12小时','measurement':'包括审核，单独记录维护工时'}],
            'stop_conditions':'严重错误立即停止','owner':'测试负责人','resources':'工程和客服排期',
            'cash_budget':2800,'internal_cost':5200,'max_loss':8000,'loss_estimate':8000,
            'planned_start':'2026-09-10','duration_days':28,'checkin_after_days':7,'records':'工单、抽查表及工时记录'}


def project():
    return {'version':1,'lifecycle':lc.initial()}


def review(p,conclusion='trial'):
    p['lifecycle']['review']={'conclusion':conclusion}
    return p


def test_dates_trigger_followup_not_stage_and_actual_start_anchors_schedule(monkeypatch):
    monkeypatch.setattr(lc,'today',lambda:date(2026,9,12))
    p=lc.transition(review(project()),'confirm_plan',{'plan':plan()},case()[1])
    assert lc.followup(p)['due'] and p['lifecycle']['stage']=='pre'
    p=lc.transition(p,'start',{'date':'2026-09-12'},case()[1])
    assert p['lifecycle']['next_review_on']=='2026-09-19'
    assert p['lifecycle']['expected_end']=='2026-10-10'
    assert lc.followup(p,date(2027,1,1))['due']
    assert p['lifecycle']['stage']=='during'


def test_cannot_start_without_plan_or_on_future_date():
    with pytest.raises(ValueError):lc.transition(project(),'start',{'date':'2026-09-10'},case()[1])
    p=lc.transition(review(project()),'confirm_plan',{'plan':plan()},case()[1])
    with pytest.raises(ValueError):lc.transition(p,'start',{'date':'2099-01-01'},case()[1])


def test_budget_and_loss_are_separate_and_plan_history_immutable():
    p=lc.transition(review(project()),'confirm_plan',{'plan':plan()},case()[1])
    old=deepcopy(p['lifecycle']['plan'])
    amended={**plan(),'cash_budget':3000,'duration_days':35}
    with pytest.raises(ValueError):lc.transition(p,'confirm_plan',{'plan':amended},case()[1])
    p=lc.transition(p,'confirm_plan',{'plan':amended,'reason':'追加记录一周'},case()[1])
    assert p['lifecycle']['plan_history'][0]==old
    assert p['lifecycle']['plan']['version']==2
    for invalid in ({'cash_budget':200000},{'loss_estimate':8001}):
        with pytest.raises(ValueError):lc.transition(review(project()),'confirm_plan',{'plan':{**plan(),**invalid}},case()[1])


def test_early_end_pause_and_reschedule(monkeypatch):
    monkeypatch.setattr(lc,'today',lambda:date(2026,9,15))
    p=lc.transition(review(project()),'confirm_plan',{'plan':plan()},case()[1])
    p=lc.transition(p,'start',{'date':'2026-09-10'},case()[1])
    p=lc.transition(p,'pause',{'reason':'等待记录'},case()[1]);assert lc.followup(p) is None
    p=lc.transition(p,'resume',{'reason':'记录已补'},case()[1]);assert lc.followup(p)['due']
    p=lc.transition(p,'schedule',{'date':'2026-09-18','reason':'延期回访'},case()[1])
    assert p['lifecycle']['expected_end']=='2026-10-08'
    p=lc.transition(p,'complete',{'date':'2026-09-15','reason':'提前停止'},case()[1])
    assert p['lifecycle']['stage']=='post' and lc.followup(p)['due']


def test_legacy_stage_requires_confirmation_and_model_cannot_transition():
    p={'version':1}
    r={'stage_review':{'conclusion':'trial','summary':'test','next_action':'test'},'pilot_plan':plan()}
    lc.absorb(p,r,{},[])
    assert not p['lifecycle']['confirmed'] and p['lifecycle']['plan'] is None
    assert not p['lifecycle'].get('review')


def test_future_results_do_not_block_initial_review_but_unanswered_questions_do():
    p=project()
    coverage={k:{'status':'future' if k=='return' else 'known','reason':'目标待试点验证' if k=='return' else '用户已说明'} for k in DIMENSIONS}
    r={'dimension_coverage':coverage,'stage_review':{'conclusion':'trial','summary':'有合理价值路径','next_action':'开始小范围验证'}}
    lc.absorb(p,r,case()[1],[])
    assert p['lifecycle']['review']['conclusion']=='trial'
    coverage['market']['status']='ask'
    lc.absorb(p,r,case()[1],[])
    assert p['lifecycle']['review']['conclusion']=='needs_info'


def test_verified_veto_precedes_missing_dimensions_and_unverified_does_not():
    evidence=[{'id':'v1','verification_status':'verified','source_locator':'用户确认记录'}]
    proposal={'vetoes':[{'reason':'关键资源明确无法取得且无替代','confirmed':True,'evidence_ids':['v1']}]}
    assert assess({}, {}, evidence,proposal)['grade']=='C'
    evidence[0]['verification_status']='unverified'
    assert assess({}, {}, evidence,proposal)['grade']=='NR'
    evidence[0].update(verification_status='verified',valid_until='2000-01-01')
    assert assess({}, {}, evidence,proposal)['grade']=='NR'


def test_lifecycle_context_keeps_plan_and_coverage_not_full_history():
    p=project();p['lifecycle'].update(plan=plan(),coverage={'market':{'status':'known','reason':'600单每月'}},reviews=[{'summary':str(i)} for i in range(20)])
    c=model_context(p,{},[],[{'content':str(i)} for i in range(50)])
    assert c['project']['lifecycle']['plan']==plan()
    assert c['project']['lifecycle']['coverage']['market']['reason']=='600单每月'
    assert len(c['project']['lifecycle']['recent_reviews'])==3
    assert 'plan_history' not in c['project']['lifecycle']


def test_http_stage_transition_requires_version_and_final_scoring_requires_post(client):
    p=client.post('/api/projects',json={'name':'合成阶段测试'}).json();pid=p['id']
    assert client.post(f'/api/projects/{pid}/assess',json={}).status_code==422
    action={'action':'set_stage','version':p['version'],'payload':{'stage':'post','actual_start':'2026-09-01','actual_end':'2026-09-05'}}
    response=client.post(f'/api/projects/{pid}/lifecycle',json=action)
    assert response.status_code==200 and response.json()['lifecycle']['stage']=='post'
    assert client.post(f'/api/projects/{pid}/lifecycle',json=action).status_code==409
    assert client.post(f'/api/projects/{pid}/assess',json={}).json()['result']['grade']=='NR'


def test_scheduling_preserves_existing_report_and_proposal(client):
    p=client.post('/api/projects',json={'name':'合成回访测试'}).json();pid=p['id']
    from sabc import app as module
    p=module.store.save('projects',{**p,'last_grade':'B','proposal':{'test':'retained'},'interview':{'state':'ready'}})
    result=client.post(f'/api/projects/{pid}/lifecycle',json={'action':'schedule','version':p['version'],'payload':{'date':lc.today().isoformat(),'reason':'补充记录'}}).json()
    assert result['last_grade']=='B' and result['proposal']==p['proposal'] and result['interview']==p['interview']
