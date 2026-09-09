import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from sabc import collector_service
from sabc.remote_collector import collect_remote
from sabc.store import Store


@pytest.fixture
def configured(tmp_path,monkeypatch):
    monkeypatch.setenv('SABC_COLLECTOR_URL','https://collector.example:8443')
    monkeypatch.setenv('SABC_COLLECTOR_TOKEN','x'*40)
    monkeypatch.delenv('SABC_COLLECTOR_CA_B64',raising=False)
    return Store(tmp_path/'test.db')


def payload():
    return {'status':'success','job_id':'job-1','collector_region':'ap-shanghai',
            'evidence':{'id':'remote-id','project_id':'remote-job','title':'github · a/b','source_id':'github','query':'a/b','source_locator':'https://api.github.com/repos/a/b','content':'{"facts": {"full_name":"a/b"}}','data_period':'2026-09-10 快照','scope':'公开仓库，不能证明收入','retrieved_at':'2026-09-10T00:00:00Z','payload_sha256':'a'*64,'level':3,'verification_status':'verified'},
            'runs':[{'id':'remote-run','project_id':'remote-job','source':'github','query':'a/b','status':'success','attempt':1,'evidence_id':'remote-id'}]}


def transport(monkeypatch,handler):
    original=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))


def test_remote_result_saves_locally_without_trusting_evidence_level(configured,monkeypatch):
    def handler(request):
        assert request.headers['authorization']=='Bearer '+'x'*40
        assert json.loads(request.content)=={'source':'github','query':'a/b'}
        return httpx.Response(200,json=payload())
    transport(monkeypatch,handler)
    result=collect_remote(configured,'local-project','github','a/b')
    assert result['id']!='remote-id' and result['project_id']=='local-project'
    assert result['level']==0 and result['verification_status']=='unverified'
    assert result['collector_region']=='ap-shanghai'
    assert configured.list('source_runs')[0]['evidence_id']==result['id']


def test_remote_mismatch_is_not_evidence(configured,monkeypatch):
    wrong=payload();wrong['evidence']['query']='other/repo'
    transport(monkeypatch,lambda r:httpx.Response(200,json=wrong))
    with pytest.raises(ValueError,match='不一致'):collect_remote(configured,'p','github','a/b')
    assert not configured.list('evidence')


def test_remote_failure_does_not_retry_or_fallback(configured,monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(504,json={'detail':'timeout'})
    transport(monkeypatch,handler)
    with pytest.raises(ValueError,match='504'):collect_remote(configured,'p','github','a/b')
    assert len(calls)==1 and not configured.list('evidence')


def test_service_auth_validation_and_busy(monkeypatch):
    monkeypatch.setenv('SABC_COLLECTOR_TOKEN','x'*40)
    client=TestClient(collector_service.app)
    assert client.get('/v1/health').status_code==401
    headers={'Authorization':'Bearer '+'x'*40}
    assert client.get('/v1/health',headers=headers).json()['region']=='ap-shanghai'
    assert client.post('/v1/collect',headers=headers,json={'source':'stats','query':'https://evil.example/a.html'}).status_code==422
    monkeypatch.setattr(collector_service,'slots',asyncio.Semaphore(0))
    assert client.post('/v1/collect',headers=headers,json={'source':'github','query':'a/b'}).status_code==429


def test_service_hard_timeout_kills_worker(monkeypatch):
    monkeypatch.setenv('SABC_COLLECTOR_TOKEN','x'*40)
    monkeypatch.setattr(collector_service,'slots',asyncio.Semaphore(2))
    monkeypatch.setattr(collector_service,'JOB_TIMEOUT',0.01)
    class Process:
        returncode=None
        killed=False
        async def wait(self):
            if not self.killed: await asyncio.sleep(10)
        def kill(self): self.killed=True;self.returncode=-9
    process=Process()
    async def spawn(*args,**kwargs):return process
    monkeypatch.setattr(asyncio,'create_subprocess_exec',spawn)
    r=TestClient(collector_service.app).post('/v1/collect',headers={'Authorization':'Bearer '+'x'*40},json={'source':'github','query':'a/b'})
    assert r.status_code==504 and process.killed
