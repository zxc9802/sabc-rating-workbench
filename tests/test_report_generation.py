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
        calls.append('analysis');r=draft_reply();r['project_patch']=patch or {};return r
    monkeypatch.setattr(module,'analyze',analyze)
    url='/api/projects/'+project['id']
    assert client.post(url+'/chat',json={'message':'最后一条信息'}).status_code==200
    return module,url,calls


def test_one_analysis_then_explicit_generation(client,monkeypatch):
    module,url,calls=prepare(client,monkeypatch)
    detail=client.get(url).json()
    assert calls==['analysis'] and detail['project']['report_ready']
    assert 'assessment_review' not in detail['project'] and detail['assessments']==[]
    assert not hasattr(module,'review_report')
    monkeypatch.setattr(module,'analyze',lambda *a:pytest.fail('点击后不应再调用模型'))
    assert client.post(url+'/chat',json={'message':'生成','generate_report':True}).json()['report_id']
    assert len(client.get(url).json()['assessments'])==1


@pytest.mark.parametrize('change',['project','company','evidence','proposal'])
def test_changed_inputs_require_updated_judgment(client,monkeypatch,change):
    module,url,calls=prepare(client,monkeypatch)
    if change=='company':client.put('/api/company',json={'strategy':'新战略'})
    elif change=='evidence':module.store.save('evidence',{'project_id':url.split('/')[-1],'title':'新证据'})
    else:
        p=module.store.get('projects',url.split('/')[-1])
        if change=='proposal':p['proposal']['pros']=['修改过的判断']
        else:p['risks']='新增风险'
        module.store.save('projects',p)
    assert not client.get(url).json()['project']['report_ready']
    assert client.post(url+'/chat',json={'message':'生成','generate_report':True}).json()['needs_collection']
    assert calls==['analysis']


def test_confirm_pending_facts_without_repeat_analysis(client,monkeypatch):
    module,url,calls=prepare(client,monkeypatch,{'risks':'新风险'})
    assert not client.get(url).json()['project']['report_ready']
    assert client.post(url+'/chat',json={'message':'生成','generate_report':True}).json()['needs_fact_confirmation']
    assert client.patch(url,json={'risks':'新风险'}).status_code==200
    assert client.get(url).json()['project']['report_ready']
    assert calls==['analysis']


def test_old_prepared_project_does_not_need_review_again(client,monkeypatch):
    module,url,_=prepare(client,monkeypatch)
    p=module.store.get('projects',url.split('/')[-1]);saved=p.pop('report_preparation')
    p['assessment_review']={'revised_proposal':saved['proposal'],'input_fingerprint':saved['input_fingerprint']}
    module.store.save('projects',p)
    assert client.get(url).json()['project']['report_ready']
