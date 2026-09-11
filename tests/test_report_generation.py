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
