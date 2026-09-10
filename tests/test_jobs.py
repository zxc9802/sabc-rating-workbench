from threading import Event
from uuid import uuid4
import time

import pytest
from fastapi import HTTPException
from sabc.jobs import Jobs
from sabc.store import Store
from tests.test_app import client


def terminal(client,ident):
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        data=client.get('/api/jobs/'+ident).json()
        if data['status']!='running': return data
        time.sleep(.01)
    raise AssertionError('job did not finish')


def test_slow_source_returns_immediately_and_duplicate_resumes(client,monkeypatch):
    import sabc.app as module
    started=Event(); release=Event(); calls=[]
    def collect(store,pid,source,query):
        calls.append(query); started.set()
        assert release.wait(3)
        return {'title':'saved once'}
    monkeypatch.setattr(module,'collect',collect)
    pid=client.post('/api/projects',json={'name':'jobs'}).json()['id']
    ident=str(uuid4())
    body={'id':ident,'operation':'source','source':'github','payload':{'query':'fastapi/fastapi'}}
    try:
        response=client.post(f'/api/projects/{pid}/jobs',json=body)
        assert response.status_code==202
        assert started.wait(1)
        assert response.json()['status']=='running'
        assert client.post(f'/api/projects/{pid}/jobs',json=body).json()['id']==ident
        assert client.get(f'/api/projects/{pid}').json()['active_jobs'][0]['id']==ident
        changed={**body,'payload':{'query':'different/repo'}}
        assert client.post(f'/api/projects/{pid}/jobs',json=changed).status_code==409
    finally: release.set()
    assert terminal(client,ident)['result']=={'title':'saved once'}
    assert calls==['fastapi/fastapi']
    assert not client.get(f'/api/projects/{pid}').json()['active_jobs']


def test_failure_is_retrievable_after_original_request_ends(client,monkeypatch):
    import sabc.app as module
    def fail(*args): raise ValueError('上海采集连接失败（HTTP 504），未返回证据')
    monkeypatch.setattr(module,'collect',fail)
    pid=client.post('/api/projects',json={'name':'failed job'}).json()['id']
    ident=str(uuid4())
    client.post(f'/api/projects/{pid}/jobs',json={'id':ident,'operation':'source','source':'github','payload':{'query':'a/b'}})
    result=terminal(client,ident)
    assert result['status']=='success' and result['result']=={'status':'skipped'}
    assert '504' in module.store.list('source_runs')[0]['error']
    assert not client.get(f'/api/projects/{pid}').json()['evidence']


def test_restart_records_interruption_without_replaying(tmp_path):
    store=Store(tmp_path/'jobs.db'); manager=Jobs()
    store.save('jobs',{'id':'j','project_id':'p','process_id':'old','status':'running'})
    result=manager.read(store,'j')
    assert result['status']=='failed' and '重新启动' in result['error']
    assert store.get('jobs','j')['status']=='failed'
    manager.pool.shutdown()


def test_capacity_and_same_project_reject_extra_work(tmp_path):
    store=Store(tmp_path/'jobs.db'); manager=Jobs(); release=Event()
    try:
        manager.submit(store,'a','p',{},lambda:release.wait(3))
        with pytest.raises(HTTPException) as error: manager.submit(store,'b','p',{},lambda:None)
        assert error.value.status_code==409
        manager.submit(store,'c','q',{},lambda:release.wait(3))
        with pytest.raises(HTTPException) as error: manager.submit(store,'d','r',{},lambda:None)
        assert error.value.status_code==429
    finally:
        release.set(); manager.pool.shutdown()


def test_queue_cancel_and_late_completion(tmp_path):
    store=Store(tmp_path/'queue.db'); manager=Jobs(); release=Event(); called=[]
    try:
        manager.submit(store,'a','p',{},lambda:release.wait(3))
        manager.submit(store,'b','q',{},lambda:release.wait(3))
        queued=manager.submit(store,'c','r',{},lambda:called.append('c'),queue=True)
        assert queued['phase']=='queued'
        assert manager.cancel(store,'c')['status']=='cancelled'
        assert manager.cancel(store,'a')['status']=='cancelled'
        release.set();manager.pool.shutdown()
        assert called==[]
        assert manager.read(store,'a')['status']=='cancelled'
        assert manager.read(store,'b')['status']=='success'
        assert manager.cancel(store,'b')['status']=='success'
    finally:
        release.set();manager.pool.shutdown()


def test_initial_interview_submitted_once_and_explicit_retry(client,monkeypatch):
    import sabc.app as module
    manager=Jobs();monkeypatch.setattr(module,'jobs',manager)
    started=Event();release=Event();calls=[]
    def chat(pid,body):
        calls.append(body.message);started.set();release.wait(3)
        return {}
    monkeypatch.setattr(module,'chat',chat)
    try:
        p=client.post('/api/projects',json={'name':'auto','description':'first idea','auto_start':True}).json()
        assert started.wait(1)
        first=client.post(f"/api/projects/{p['id']}/start-interview").json()
        assert first['status']=='running'
        assert client.post(f"/api/projects/{p['id']}/start-interview").json()['id']==first['id']
        assert client.post('/api/jobs/'+first['id']+'/cancel').json()['status']=='cancelled'
        assert client.post(f"/api/projects/{p['id']}/start-interview").json()['status']=='cancelled'
        release.set();manager.pool.shutdown()
        assert calls==['first idea']
    finally:
        release.set();manager.pool.shutdown()
