import json
import time
from threading import Event
from uuid import uuid4
import pytest
from fastapi import HTTPException
from tests.test_app import client
from sabc import report_qa
from sabc.tenancy import AccountStore, account_id
from sabc.streaming import cancel_signal, JobCancelled


def seed(store, pid='p', rid='r'):
    store.save('projects', {'id':pid,'messages':[{'role':'user','content':'访谈原文'}]})
    return store.save('assessments', {'id':rid,'project_id':pid,'result':{'grade':'B'},
        'snapshot':{'project':{'description':'原报告项目'},'company':{},'proposal':{},'evidence':[]}})


def test_model_uses_selected_snapshot_and_exact_model(monkeypatch):
    report={'result':{'grade':'B'},'snapshot':{'project':{'description':'历史版本','messages':['不可重复传入']},'evidence':[]}}
    seen={}
    def complete(client,url,payload,headers,remaining):
        seen.update(payload)
        assert url=='https://model.example/v1/chat/completions'
        return json.dumps({'reply':'这份报告建议小额验证'})
    monkeypatch.setattr(report_qa,'completion',complete)
    assert report_qa.answer({'base_url':'https://model.example/v1','model':'other'},'test',report,[{'question':'上一个问题','reply':'上一个回答'}],'为什么B')
    assert seen['model']=='glm-5.3-flash'
    assert '历史版本' in seen['messages'][1]['content']
    assert '不可重复传入' not in seen['messages'][1]['content']
    assert seen['messages'][-3:]==[{'role':'user','content':'上一个问题'},{'role':'assistant','content':'上一个回答'},{'role':'user','content':'为什么B'}]


def test_job_saves_separate_history_and_retry_is_idempotent(client, monkeypatch):
    import sabc.app as module
    report=seed(module.store)
    module.store.save('assessments',{**report,'id':'r2','result':{'grade':'A'}})
    before=module.store.get('projects','p')
    calls=[]
    def answer(s,k,r,h,q):
        calls.append(r['id']); assert r['result']['grade']=='B'; return '解释B级依据'
    monkeypatch.setattr(report_qa,'answer',answer)
    request={'id':str(uuid4()),'operation':'report_chat','payload':{'assessment_id':'r','message':'为什么B'}}
    response=client.post('/api/projects/p/jobs',json=request)
    assert response.status_code==202
    for _ in range(100):
        job=client.get('/api/jobs/'+request['id']).json()
        if job['status']!='running': break
        time.sleep(.01)
    assert job['status']=='success',job
    assert client.post('/api/projects/p/jobs',json=request).status_code==202
    assert calls==['r']
    history=client.get('/api/projects/p/reports/r/chat').json()
    assert len(history['turns'])==1 and history['turns'][0]['reply']=='解释B级依据'
    assert client.get('/api/projects/p/reports/r2/chat').json()['turns']==[]
    assert module.store.get('projects','p')==before
    assert module.store.get('assessments','r')==report
    seed(module.store,'p2','other')
    bad={**request,'id':str(uuid4()),'payload':{'assessment_id':'other','message':'跨项目'}}
    assert client.post('/api/projects/p/jobs',json=bad).status_code==404
    assert client.get('/api/projects/p/reports/other/chat').status_code==404
    assert client.post('/api/projects/p/jobs',json={**bad,'payload':{'assessment_id':'r','message':'  '}}).status_code==422


def test_account_isolation_and_cancellation(tmp_path,monkeypatch):
    import sabc.app as module
    store=AccountStore(tmp_path/'db.sqlite');monkeypatch.setattr(module,'store',store)
    token=account_id.set('owner')
    try:
        seed(store)
        monkeypatch.setattr(report_qa,'answer',lambda *args:'回答')
        body=module.ReportQuestion(assessment_id='r',message='问题')
        signal=Event();signal.set();cancel=cancel_signal.set(signal)
        try:
            with pytest.raises(JobCancelled): module.report_chat('p',body,'job')
        finally: cancel_signal.reset(cancel)
        assert store.list('report_turns')==[]
        module.report_chat('p',body,'job')
        account_id.set('other')
        with pytest.raises(HTTPException) as error: module.report_history('p','r')
        assert error.value.status_code==404
        assert store.list('report_turns')==[]
    finally: account_id.reset(token)


def test_failure_does_not_save_a_turn(client,monkeypatch):
    import sabc.app as module
    seed(module.store)
    def fail(*args): raise ValueError('回答失败')
    monkeypatch.setattr(report_qa,'answer',fail)
    with pytest.raises(ValueError): module.report_chat('p',module.ReportQuestion(assessment_id='r',message='问题'),'job')
    assert module.store.list('report_turns')==[]


def test_active_answer_recovers_only_in_report(client,monkeypatch):
    import sabc.app as module
    seed(module.store)
    module.store.save('jobs',{'id':'pending','project_id':'p','assessment_id':'r','operation':'report_chat',
        'question':'试点怎么做','status':'running','process_id':module.jobs.process_id})
    history=client.get('/api/projects/p/reports/r/chat').json()
    assert history['active_job']['question']=='试点怎么做'
    assert client.get('/api/projects/p').json()['active_jobs']==[]


@pytest.mark.parametrize('reply',['{}','{"reply":""}','{"reply":42}','not json'])
def test_invalid_model_output_is_not_accepted(monkeypatch,reply):
    monkeypatch.setattr(report_qa,'completion',lambda *args:reply)
    with pytest.raises(ValueError,match='未完成'):
        report_qa.answer({'base_url':'https://model.example'},'test',{'result':{},'snapshot':{}},[],'问题')


def test_report_qa_uses_same_fallback_chain(monkeypatch):
    monkeypatch.setenv('SABC_DEEPSEEK_API_KEY','synthetic-deepseek')
    monkeypatch.setenv('SABC_DEEPSEEK_MODEL','deepseek-flash')
    seen=[]
    def complete(client,url,payload,headers,remaining):
        seen.append(payload['model'])
        if payload['model']!='deepseek-flash':
            assert url=='https://provider.example/v1/chat/completions'
            assert headers['Authorization']=='Bearer synthetic-shared'
            raise ValueError('invalid response')
        assert headers['Authorization']=='Bearer synthetic-deepseek'
        assert payload['thinking']=={'type':'enabled'}
        return json.dumps({'reply':'根据这份报告说明'})
    monkeypatch.setattr(report_qa,'completion',complete)
    report={'result':{'grade':'B'},'snapshot':{}}
    assert report_qa.answer({'base_url':'https://provider.example/v1'},'synthetic-shared',report,[],'为什么')=='根据这份报告说明'
    assert seen==['glm-5.3-flash','glm-5.3-flash','gpt-5.6-luna','deepseek-flash']
