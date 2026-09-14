from copy import deepcopy
from threading import Event
from uuid import uuid4
import pytest
from tests.test_app import client
from tests.test_rating import case
from tests.report_fixtures import draft_reply


def accepted():
    return {'checks': {k:'pass' for k in ('facts','business','risk','consistency')}, 'findings':[],
            'project_patch':{}, 'coverage_reasons':{}, 'coverage_statuses':{}, 'framing':None,
            'questions':[], 'proposal':None, 'stage_review':None}


def prepare(client,monkeypatch):
    import sabc.app as module
    from sabc import advisory
    p,c,_,_=case();client.put('/api/company',json=c)
    project=client.post('/api/projects',json=p).json();calls=[]
    monkeypatch.setattr(module,'settings',lambda:{'base_url':'https://model.example','model':'test'})
    def analyze(*args):
        calls.append('draft' if args[2].get('_report_requested') else 'interview')
        reply=draft_reply()
        for item in list(reply['proposal']['dimensions'].values())+reply['proposal']['assumptions']:
            item['evidence_ids']=[]
        return reply
    monkeypatch.setattr(module,'analyze',analyze)
    monkeypatch.setattr(advisory,'_request',lambda *args:accepted())
    return module,advisory,'/api/projects/'+project['id'],calls


def send(client,url,**payload):
    return client.post(url+'/chat',json={'message':'最后一条信息',**payload})


def test_interview_private_draft_review_final_and_idempotent_retry(client,monkeypatch):
    module,advisory,url,calls=prepare(client,monkeypatch)
    analyze=module.analyze
    def inspect_draft(*args):
        if args[2].get('_report_requested'):
            detail=client.get(url).json()
            assert detail['project']['report_pipeline']['step']=='preparing'
            assert detail['project']['report_ready'] and not detail['assessments']
            assert detail['project']['proposal'] is None
        return analyze(*args)
    monkeypatch.setattr(module,'analyze',inspect_draft)
    def inspect_review(*args):
        calls.append('review')
        detail=client.get(url).json()
        assert detail['project']['report_pipeline']=={'step':'reviewing','report_id':None}
        assert not detail['assessments'] and detail['project']['proposal'] is None
        assert detail['project']['lifecycle'].get('review') is None
        assert client.get('/api/bootstrap').json()['projects'][0]['proposal'] is None
        return accepted()
    monkeypatch.setattr(advisory,'_request',inspect_review)
    response=send(client,url)
    assert response.status_code==200,response.text
    detail=client.get(url).json()
    assert calls==['interview','draft','review']
    assert len(detail['assessments'])==1
    assert detail['project']['report_pipeline']['step']=='complete'
    for payload in ({},{'message':'继续处理','generate_report':True}):
        assert send(client,url,**payload).json()['report_id']==response.json()['report_id']
    assert calls==['interview','draft','review']
    assert len(client.get(url).json()['assessments'])==1


@pytest.mark.parametrize('step',['draft','review','verification'])
def test_failure_resumes_only_unfinished_step(client,monkeypatch,step):
    module,advisory,url,calls=prepare(client,monkeypatch)
    original=module.analyze; failed=False; reviews=[]
    def analyze(*args):
        nonlocal failed
        if args[2].get('_report_requested') and step=='draft' and not failed:
            failed=True; calls.append('draft'); raise ValueError('模拟超时')
        return original(*args)
    def review(settings,key,context):
        nonlocal failed
        reviews.append(deepcopy(context))
        if step=='verification' and not context['previous_findings']:
            result=accepted();result['checks']['facts']='revise'
            result['findings']=[{'perspective':'facts','target':'proposal.market','source_id':'turn-0','quote':'最后一条信息','reason':'测试修订'}]
            result['proposal']=deepcopy(context['candidate']['proposal'])
            result['proposal']['dimensions']['market'].update(score=None,basis='unknown',reason='市场依据尚未取得')
            return result
        if step!='draft' and not failed:
            failed=True;raise ValueError('模拟超时')
        return accepted()
    monkeypatch.setattr(module,'analyze',analyze);monkeypatch.setattr(advisory,'_request',review)
    assert send(client,url).status_code==422
    detail=client.get(url).json()
    assert detail['project']['report_ready'] and not detail['assessments']
    assert detail['project']['proposal'] is None
    assert detail['project']['report_pipeline']['step']=={'draft':'preparing','review':'reviewing','verification':'revising'}[step]
    assert send(client,url,message='继续处理',generate_report=True).status_code==200
    detail=client.get(url).json()
    assert len(detail['assessments'])==1 and calls.count('interview')==1
    assert calls.count('draft')==(2 if step=='draft' else 1)
    assert sum(m['role']=='user' for m in detail['project']['messages'])==1
    if step=='verification':
        assert reviews[-1]['previous_findings'] and reviews[-1]['candidate']['result']['grade']=='NR'
        assert detail['assessments'][0]['result']['grade']=='NR'


@pytest.mark.parametrize('change',['project','company','evidence'])
def test_changed_inputs_discard_draft_and_require_interview(client,monkeypatch,change):
    module,advisory,url,calls=prepare(client,monkeypatch)
    def fail(*args): raise ValueError('模拟超时')
    monkeypatch.setattr(advisory,'_request',fail)
    assert send(client,url).status_code==422
    if change=='company':client.put('/api/company',json={'strategy':'新战略'})
    elif change=='evidence':module.store.save('evidence',{'project_id':url.split('/')[-1],'title':'新证据'})
    else:client.patch(url,json={'risks':'新增风险'})
    detail=client.get(url).json()
    assert detail['project']['report_pipeline'] is None and not detail['project']['report_ready']
    assert send(client,url,generate_report=True).json()['needs_collection']
    assert calls==['interview','draft'] and not detail['assessments']


@pytest.mark.parametrize('step',['draft','review'])
def test_changes_during_processing_cannot_publish(client,monkeypatch,step):
    module,advisory,url,calls=prepare(client,monkeypatch)
    original=module.analyze
    def change():client.put('/api/company',json={'strategy':'处理期间的新战略'})
    def analyze(*args):
        if args[2].get('_report_requested') and step=='draft':change()
        return original(*args)
    def review(*args):change();return accepted()
    monkeypatch.setattr(module,'analyze',analyze)
    if step=='review':monkeypatch.setattr(advisory,'_request',review)
    assert send(client,url).status_code==422
    assert not client.get(url).json()['assessments']


def test_pending_question_prevents_drafting_even_with_complete_coverage(client,monkeypatch):
    module,advisory,url,calls=prepare(client,monkeypatch)
    def ask(*args):
        calls.append('interview');r=draft_reply();r.update(reply='客户是谁？',questions=['客户是谁？']);return r
    monkeypatch.setattr(module,'analyze',ask)
    assert send(client,url).status_code==200
    detail=client.get(url).json()
    assert calls==['interview'] and not detail['assessments']
    assert not detail['project']['report_ready'] and detail['project']['report_pipeline'] is None


def test_legacy_collection_stamp_cannot_start_report(client,monkeypatch):
    module,advisory,url,calls=prepare(client,monkeypatch)
    p=module.store.get('projects',url.split('/')[-1])
    p['lifecycle'].update(confirmed=True,coverage=draft_reply()['dimension_coverage'])
    p['collection_completion']={'review_version':1,'input_fingerprint':module.report_readiness.fingerprint(p,module.company(),[])}
    module.store.save('projects',p)
    assert send(client,url,generate_report=True).json()['needs_collection'] and not calls


def test_cancel_during_review_retains_private_draft_and_public_stage(client,monkeypatch):
    module,advisory,url,calls=prepare(client,monkeypatch)
    entered,release=Event(),Event()
    def pause(*args):entered.set();assert release.wait(5);return accepted()
    monkeypatch.setattr(advisory,'_request',pause)
    ident=str(uuid4())
    client.post(url+'/jobs',json={'id':ident,'operation':'chat','payload':{'message':'最后一条信息'}})
    try:
        assert entered.wait(5)
        job=client.get('/api/jobs/'+ident).json()
        assert job['collection']['report_pipeline']['step']=='reviewing'
        assert job['collection']['report_ready'] and not job.get('partial_reply')
        future=module.jobs.futures[(str(module.store.path),ident)]
        assert client.post('/api/jobs/'+ident+'/cancel').json()['status']=='cancelled'
    finally:release.set()
    future.result(timeout=5)
    detail=client.get(url).json()
    assert not detail['assessments'] and detail['project']['report_pipeline']['step']=='reviewing'
    monkeypatch.setattr(advisory,'_request',lambda *args:accepted())
    assert send(client,url,generate_report=True).status_code==200
    assert calls==['interview','draft']


def test_review_can_correct_facts_and_coverage_before_recomputing(client,monkeypatch):
    module,advisory,url,calls=prepare(client,monkeypatch)
    seen=[]
    def review(settings,key,context):
        seen.append(deepcopy(context));r=accepted()
        if len(seen)==1:
            r.update(checks={**r['checks'],'facts':'revise'},project_patch={'risks':'未取得独立风险验证'},
                     coverage_reasons={'opportunity':'当前材料未取得对照案例'},
                     findings=[{'perspective':'facts','target':'risks','source_id':'turn-0','quote':'最后一条信息','reason':'测试修订'}])
        return r
    monkeypatch.setattr(advisory,'_request',review)
    assert send(client,url).status_code==200
    detail=client.get(url).json();p=detail['assessments'][0]['snapshot']['project']
    assert len(seen)==2 and seen[1]['project']['risks']=='未取得独立风险验证'
    assert p['lifecycle']['coverage']['opportunity']['reason']=='当前材料未取得对照案例'
    assert detail['project']['report_ready']


def test_new_question_starts_new_interview_and_preserves_old_report(client,monkeypatch):
    module,advisory,url,calls=prepare(client,monkeypatch)
    assert send(client,url).status_code==200
    old=client.get(url).json()['assessments'][0]
    def ask(*args):r=draft_reply();r.update(reply='新的成本是多少？',questions=['新的成本是多少？']);return r
    monkeypatch.setattr(module,'analyze',ask)
    assert send(client,url,message='我们改变了方案').status_code==200
    detail=client.get(url).json()
    assert detail['assessments']==[old] and detail['project']['report_pipeline'] is None
    assert not detail['project']['report_ready'] and detail['project']['proposal'] is None


def test_unresolved_second_review_never_publishes(client,monkeypatch):
    module,advisory,url,calls=prepare(client,monkeypatch)
    reviews=[]
    def revise(*args):
        reviews.append(1);r=accepted();r.update(checks={**r['checks'],'facts':'revise'},
            findings=[{'reason':'待解决'}],coverage_reasons={'opportunity':'对照资料尚未取得'});return r
    monkeypatch.setattr(advisory,'_request',revise)
    assert send(client,url).status_code==422
    assert len(reviews)==2 and not client.get(url).json()['assessments']
    assert client.get(url).json()['project']['report_pipeline']['step']=='revising'


def test_retry_recovers_publication_interrupted_after_project_save(client,monkeypatch):
    module,advisory,url,calls=prepare(client,monkeypatch)
    def revise(settings,key,context):
        r=accepted()
        if not context['previous_findings']:
            r.update(checks={**r['checks'],'facts':'revise'},project_patch={'risks':'纠正后的风险'},findings=[{'reason':'测试修订'}])
        return r
    monkeypatch.setattr(advisory,'_request',revise)
    save=module.store.save
    def interrupted(kind,record):
        if kind=='report_workflows' and record.get('step')=='complete':raise ValueError('模拟最终发布时进程中断')
        return save(kind,record)
    monkeypatch.setattr(module.store,'save',interrupted)
    assert send(client,url).status_code==422
    detail=client.get(url).json()
    assert len(detail['assessments'])==1 and detail['project']['report_pipeline']['step']=='complete'
    assert send(client,url,generate_report=True).json()['report_id']==detail['assessments'][0]['id']
    assert calls==['interview','draft'] and len(client.get(url).json()['assessments'])==1


@pytest.mark.parametrize('change',['company','evidence'])
def test_completed_report_cannot_restore_old_stage_after_sources_change(client,monkeypatch,change):
    module,advisory,url,calls=prepare(client,monkeypatch)
    assert send(client,url).status_code==200
    if change=='company':client.put('/api/company',json={'strategy':'新的公司战略'})
    else:module.store.save('evidence',{'project_id':url.split('/')[-1],'title':'新证据'})
    detail=client.get(url).json()
    assert detail['project']['report_pipeline'] is None and not detail['project']['report_ready']
    assert send(client,url,generate_report=True).json()['needs_collection']
    assert len(detail['assessments'])==1
