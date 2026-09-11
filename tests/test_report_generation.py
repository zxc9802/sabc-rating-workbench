from copy import deepcopy
import pytest
from tests.test_app import client
from tests.test_rating import case
from tests.test_advisory_review import draft_reply
from sabc.streaming import progress


def prepare(client, monkeypatch, patch=None, outcome='success'):
    import sabc.app as module
    p,c,_,_=case()
    client.put('/api/company',json=c)
    project=client.post('/api/projects',json=p).json()
    monkeypatch.setattr(module,'settings',lambda:{'base_url':'https://model.example','model':'test'})
    calls=[]
    def analyze(*args):
        calls.append('analysis');assert args[2]['_prepare_report']
        result=draft_reply();result['project_patch']=patch or {};return result
    def review(*args):
        calls.append('review')
        if outcome=='failure': raise ValueError('审查未完成')
        result=deepcopy(args[-1]);result['review_notes']=[{'perspective':v,'finding':'核对依据','evidence_ids':[]} for v in ('value','execution','risk')]
        if outcome=='empty': result['proposal']=None
        if outcome=='ask':
            result.update(proposal=None,stage_review=None,questions=['实际获客成本是多少？'],reply='实际获客成本是多少？')
            result['dimension_coverage']['market']={'status':'ask','reason':'尚可补充成本'}
        return result
    monkeypatch.setattr(module,'analyze',analyze);monkeypatch.setattr(module,'review_report',review)
    url='/api/projects/'+project['id']
    response=client.post(url+'/chat',json={'message':'最后一条访谈信息'})
    return module,url,calls,response


def test_click_saves_reviewed_report_without_any_model_or_retrieval(client,monkeypatch):
    module,url,calls,response=prepare(client,monkeypatch)
    assert response.status_code==200,response.text
    assert calls==['analysis','review']
    assert module.store.list('assessments')==[]
    assert client.get(url).json()['project']['report_ready']
    monkeypatch.setattr(module,'analyze',lambda *a:pytest.fail('点击后不应分析'))
    monkeypatch.setattr(module,'review_report',lambda *a:pytest.fail('点击后不应审查'))
    monkeypatch.setattr(module,'collect',lambda *a:pytest.fail('点击后不应抓取'))
    shown=[];token=progress.set(shown.append)
    try: result=module.chat(url.split('/')[-1],module.Chat(message='生成确认',generate_report=True))
    finally: progress.reset(token)
    report=module.store.get('assessments',result['report_id'])
    assert report['snapshot']['project']['assessment_review']['approved']
    assert shown==['正在生成报告…']
    assert all(m['content']!='生成确认' for m in report['snapshot']['project']['messages'])


@pytest.mark.parametrize('outcome',['ask','empty','failure'])
def test_review_problems_prevent_generate_button_and_report(client,monkeypatch,outcome):
    module,url,calls,response=prepare(client,monkeypatch,outcome=outcome)
    assert response.status_code==(200 if outcome=='ask' else 422)
    detail=client.get(url).json()
    assert not detail['project']['report_ready'] and not detail['assessments']
    if outcome=='ask': assert detail['project']['messages'][-1]['content']=='实际获客成本是多少？'
    before=list(calls)
    assert client.post(url+'/chat',json={'message':'生成','generate_report':True}).json()['needs_review']
    assert calls==before


@pytest.mark.parametrize('change',['project','company','evidence','proposal','new_input'])
def test_changed_inputs_invalidate_approval(client,monkeypatch,change):
    module,url,calls,response=prepare(client,monkeypatch)
    p=client.get(url).json()['project'];assert p['report_ready']
    if change=='project': client.patch(url,json={'risks':'新风险'})
    elif change=='company': client.put('/api/company',json={'strategy':'新战略'})
    elif change=='evidence': module.store.save('evidence',{'project_id':p['id'],'title':'新资料','content':'新事实'})
    elif change=='proposal':
        stored=module.store.get('projects',p['id']);stored['proposal']['pros']=['修改了判断'];module.store.save('projects',stored)
    else:
        def fail(*a): raise ValueError('模型暂不可用')
        monkeypatch.setattr(module,'analyze',fail)
        assert client.post(url+'/chat',json={'message':'补充新信息'}).status_code==422
    assert not client.get(url).json()['project']['report_ready']
    before=list(calls)
    assert client.post(url+'/chat',json={'message':'生成','generate_report':True}).json()['needs_review']
    assert calls==before and not module.store.list('assessments')


def test_confirming_unchanged_extracted_facts_preserves_review(client,monkeypatch):
    module,url,calls,response=prepare(client,monkeypatch,patch={'risks':'已审查的新风险'})
    assert response.status_code==200,response.text
    detail=client.get(url).json()
    assert detail['project']['review_complete'] and not detail['project']['report_ready']
    assert client.post(url+'/chat',json={'message':'生成','generate_report':True}).json()['needs_fact_confirmation']
    client.patch(url,json={'risks':'已审查的新风险'})
    assert client.get(url).json()['project']['report_ready']
    assert client.post(url+'/chat',json={'message':'生成','generate_report':True}).json()['report_id']
    assert calls==['analysis','review']


def test_prepared_model_contract_returns_internal_judgment(monkeypatch):
    import json
    import httpx
    from sabc.llm import analyze
    from sabc import lifecycle
    p,c,e,_=case()
    p.update(_prepare_report=True,_report_requested=False,lifecycle={**lifecycle.initial(),'mode':'continuous'})
    answer=draft_reply();answer.pop('mode')
    monkeypatch.delenv('SABC_DEEPSEEK_API_KEY',raising=False)
    monkeypatch.setattr(httpx.Client,'post',lambda *a,**k:httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(answer)}}]},request=httpx.Request('POST','https://model.example/chat/completions')))
    result=analyze({'base_url':'https://model.example','model':'test'},'',p,c,e,[])
    assert result['proposal'] and not result.get('report_id')


def test_edits_during_review_cannot_publish_old_approval(client,monkeypatch):
    module,url,calls,response=prepare(client,monkeypatch)
    def concurrent_edit(*args):
        current=module.store.get('projects',url.split('/')[-1])
        module.store.save('projects',{**current,'risks':'另一个窗口更新了风险'})
        return deepcopy(args[-1])
    monkeypatch.setattr(module,'review_report',concurrent_edit)
    response=client.post(url+'/chat',json={'message':'重新核对'})
    assert response.status_code==422
    assert '资料发生变化' in response.json()['detail']
    detail=client.get(url).json()
    assert detail['project']['risks']=='另一个窗口更新了风险'
    assert not detail['project']['report_ready'] and not detail['assessments']
