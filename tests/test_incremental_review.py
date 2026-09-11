from copy import deepcopy
import json
import httpx
import pytest
from tests.test_app import client
from tests.test_report_generation import prepare
from tests.test_advisory_review import draft_reply
from tests.test_rating import case
from sabc.llm import review_report


def test_followup_uses_one_review_and_preserves_generation_gate(client, monkeypatch):
    module,url,calls,_=prepare(client,monkeypatch,outcome='ask')
    initial=client.get(url).json()['project']['assessment_review']['draft']
    seen=[]
    def followup(*args):
        seen.append(args[2]['_review_followup'])
        result=deepcopy(initial)
        result['review_notes']=[{'perspective':v,'finding':'核对本次补充及关联判断','evidence_ids':[]} for v in ('value','execution','risk')]
        if len(seen)==1:
            result.update(proposal=None,stage_review=None,questions=['这个成本包含退款损失吗？'],reply='这个成本包含退款损失吗？')
            result['dimension_coverage']['cash']={'status':'ask','reason':'退款损失待明确'}
        else:
            result['proposal']['dimensions']['return'].update(score=0,basis='fact',reason='补充确认成本超过回报')
        return result
    monkeypatch.setattr(module,'analyze',lambda *a:pytest.fail('补充审查不应重写初稿'))
    monkeypatch.setattr(module,'review_report',followup)
    assert client.post(url+'/chat',json={'message':'获客成本是30元'}).status_code==200
    assert not client.get(url).json()['project']['report_ready']
    assert client.post(url+'/chat',json={'message':'生成','generate_report':True}).json()['needs_review']
    assert len(seen)==1
    assert client.post(url+'/chat',json={'message':'含退款，每单总成本已经超过收入'}).status_code==200
    detail=client.get(url).json()
    assert detail['project']['report_ready'] and not detail['assessments']
    assert seen[1]['questions']==['这个成本包含退款损失吗？']
    assert detail['project']['proposal']['dimensions']['return']['score']==0
    assert client.post(url+'/chat',json={'message':'生成','generate_report':True}).json()['report_id']
    assert len(seen)==2


@pytest.mark.parametrize('change',['company','evidence','project'])
def test_baseline_change_requires_full_review(client,monkeypatch,change):
    module,url,calls,_=prepare(client,monkeypatch,outcome='ask')
    if change=='company': client.put('/api/company',json={'strategy':'调整公司战略'})
    elif change=='project': client.patch(url,json={'risks':'增加新风险'})
    else: module.store.save('evidence',{'project_id':url.split('/')[-1],'title':'新证据','content':'新事实'})
    calls.clear()
    assert client.post(url+'/chat',json={'message':'补充审查信息'}).status_code==200
    assert calls==['analysis','review']


def test_incremental_model_extracts_pending_facts_without_rewriting_draft(monkeypatch):
    p,c,e,_=case()
    p['_review_followup']={'notes':[],'questions':['实际成本是多少？']}
    draft=draft_reply()
    answer={k:v for k,v in deepcopy(draft).items() if k!='mode'}
    answer.update(project_patch={'budget_requested':20000},proposal=None,stage_review=None,
                  questions=['是否包含退款损失？'],reply='是否包含退款损失？',
                  review_notes=[{'perspective':v,'finding':'复核新增成本及关联风险','evidence_ids':[]} for v in ('value','execution','risk')])
    answer['dimension_coverage']['cash']={'status':'ask','reason':'退款损失未明确'}
    calls=[]
    def post(*args,**kwargs):
        calls.append(kwargs['json'])
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(answer)}}]},request=httpx.Request('POST','https://model.example'))
    monkeypatch.setattr(httpx.Client,'post',post)
    monkeypatch.delenv('SABC_DEEPSEEK_API_KEY',raising=False)
    result=review_report({'base_url':'https://model.example','model':'test'},'',p,c,e,[{'role':'user','content':'预算2万'}],draft)
    assert len(calls)==1 and result['proposal'] is None
    assert result['project_patch']=={'budget_requested':20000}
    assert '必要时全面复核' in calls[0]['messages'][0]['content']
    assert json.loads(calls[0]['messages'][1]['content'])['previous_review']==p['_review_followup']
