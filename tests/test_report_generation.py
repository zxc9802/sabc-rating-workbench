from copy import deepcopy
import pytest
from tests.test_app import client
from tests.test_rating import case
from tests.report_fixtures import draft_reply


def prepare(client,monkeypatch,patch=None):
    import sabc.app as module
    p,c,_,_=case();client.put('/api/company',json=c)
    project=client.post('/api/projects',json=p).json();calls=[]
    monkeypatch.setattr(module,'settings',lambda:{'base_url':'https://model.example','model':'test'})
    def analyze(*args):
        calls.append('report' if args[2].get('_report_requested') else 'interview')
        r=draft_reply();r['project_patch']=patch or {};return r
    monkeypatch.setattr(module,'analyze',analyze)
    url='/api/projects/'+project['id']
    assert client.post(url+'/chat',json={'message':'最后一条信息'}).status_code==200
    return module,url,calls


def test_one_analysis_then_explicit_generation(client,monkeypatch):
    module,url,calls=prepare(client,monkeypatch)
    detail=client.get(url).json()
    assert calls==['interview'] and detail['project']['report_ready']
    assert detail['project']['proposal'] is None
    assert detail['project']['lifecycle'].get('review') is None
    assert 'proposal' not in detail['project']['collection_completion']
    assert detail['project']['messages'][-1]['content']=='信息已整理完成，现在生成报告吗？'
    assert 'assessment_review' not in detail['project'] and detail['assessments']==[]
    assert not hasattr(module,'review_report')
    assert client.post(url+'/chat',json={'message':'生成','generate_report':True}).json()['report_id']
    assert calls==['interview','report']
    assert len(client.get(url).json()['assessments'])==1


def test_old_completion_cannot_generate_without_new_test_history_checks(client,monkeypatch):
    from sabc.report_readiness import fingerprint
    module,url,calls=prepare(client,monkeypatch)
    project=module.store.get('projects',url.split('/')[-1])
    items=project['lifecycle']['coverage']['return']['items']
    for key in list(items):
        if key.startswith('validation_'):
            del items[key]
    project['collection_completion']['input_fingerprint']=fingerprint(project,module.company(),[])
    module.store.save('projects',project)
    assert not client.get(url).json()['project']['report_ready']
    result=client.post(url+'/chat',json={'message':'生成','generate_report':True}).json()
    assert result['needs_collection'] and calls==['interview']
    assert not client.get(url).json()['assessments']


@pytest.mark.parametrize('change',['project','company','evidence'])
def test_changed_inputs_require_updated_judgment(client,monkeypatch,change):
    module,url,calls=prepare(client,monkeypatch)
    if change=='company':client.put('/api/company',json={'strategy':'新战略'})
    elif change=='evidence':module.store.save('evidence',{'project_id':url.split('/')[-1],'title':'新证据'})
    else:
        p=module.store.get('projects',url.split('/')[-1])
        p['risks']='新增风险'
        module.store.save('projects',p)
    assert not client.get(url).json()['project']['report_ready']
    assert client.post(url+'/chat',json={'message':'生成','generate_report':True}).json()['needs_collection']
    assert calls==['interview']


def test_generate_uses_collected_facts_without_another_confirmation(client,monkeypatch):
    module,url,calls=prepare(client,monkeypatch,{'risks':'新风险'})
    assert client.get(url).json()['project']['report_ready']
    assert client.get(url).json()['assessments']==[]
    result=client.post(url+'/chat',json={'message':'生成','generate_report':True}).json()
    assert result['report_id'] and 'needs_fact_confirmation' not in result
    detail=client.get(url).json()
    assert detail['project']['risks']=='新风险' and detail['project']['pending_patch']=={}
    assert detail['assessments'][0]['snapshot']['project']['risks']=='新风险'
    assert calls==['interview','report']
    assert detail['project']['risks_source'] == 'model'
    client.patch(url, json={'risks': '用户补充的实际风险'})
    edited = client.get(url).json()['project']
    assert edited['risks_source'] == 'user'
    assert edited['risks'] == '用户补充的实际风险'


def test_pending_question_wins_over_complete_coverage(client,monkeypatch):
    module,url,calls=prepare(client,monkeypatch)
    question='持证代理的费用能退多少？'
    def ask(*args):
        calls.append('analysis')
        result=draft_reply();result.update(reply=question,questions=[question]);return result
    monkeypatch.setattr(module,'analyze',ask)
    client.post(url+'/chat',json={'message':'新的投入情况'})
    detail=client.get(url).json();p=detail['project']
    assert p['interview']['state']=='gathering'
    assert p['interview']['questions']==[question]
    assert p['messages'][-1]['content']==question
    assert not p['report_ready'] and not p['analysis_complete'] and not p['proposal']
    assert client.post(url+'/chat',json={'message':'生成','generate_report':True}).json()['needs_collection']
    assert calls==['interview','analysis'] and detail['assessments']==[]


@pytest.mark.parametrize('legacy',['report_preparation','assessment_review'])
def test_old_prepared_project_generates_fresh_report_on_click(client,monkeypatch,legacy):
    module,url,calls=prepare(client,monkeypatch)
    p=module.store.get('projects',url.split('/')[-1]);saved=p.pop('collection_completion')
    p['proposal']=draft_reply()['proposal']
    p[legacy]={'proposal' if legacy=='report_preparation' else 'revised_proposal':p['proposal'],'input_fingerprint':saved['input_fingerprint']}
    module.store.save('projects',p)
    assert client.get(url).json()['project']['report_ready']
    assert client.post(url+'/chat',json={'message':'生成','generate_report':True}).json()['report_id']
    assert calls==['interview','report']


def test_failed_generation_keeps_collection_ready_for_retry(client,monkeypatch):
    module,url,_=prepare(client,monkeypatch)
    def fail(*args): raise ValueError('模型超时')
    monkeypatch.setattr(module,'analyze',fail)
    assert client.post(url+'/chat',json={'message':'生成','generate_report':True}).status_code==422
    detail=client.get(url).json()
    assert detail['project']['report_ready'] and not detail['assessments']
    assert detail['project']['proposal'] is None
    monkeypatch.setattr(module,'analyze',lambda *args:draft_reply())
    assert client.post(url+'/chat',json={'message':'生成','generate_report':True}).json()['report_id']


def test_generation_rejects_inputs_changed_during_model_call(client,monkeypatch):
    module,url,_=prepare(client,monkeypatch)
    def change(*args):
        p=module.store.get('projects',url.split('/')[-1]);p['risks']='生成时改变的风险'
        module.store.save('projects',p)
        return draft_reply()
    monkeypatch.setattr(module,'analyze',change)
    assert client.post(url+'/chat',json={'message':'生成','generate_report':True}).status_code==422
    assert not client.get(url).json()['assessments']


@pytest.mark.parametrize('report', [False, True])
def test_chat_never_publishes_unvalidated_model_draft(monkeypatch, report):
    import sabc.app as module
    from sabc.streaming import progress
    events = []
    notify = events.append
    token = progress.set(notify)
    def turn(*args):
        progress.get()('已经回答过的报价，还要再问一次？')
        return {'reply': '报告已生成。' if report else '信息已整理完成，现在生成报告吗？'}
    monkeypatch.setattr(module, 'chat_turn', turn)
    try:
        result = module.chat('test-project', module.Chat(message='补充', generate_report=report))
        assert events == (['正在生成报告…'] if report else [result['reply']])
        assert '报价' not in result['reply']
        assert progress.get() is notify
    finally:
        progress.reset(token)
