import json
import httpx
import pytest
from sabc.llm import analyze
from sabc.schema import validate_proposal
from tests.test_rating import case


def model_response(monkeypatch,content):
    def post(*args,**kwargs):
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(content)}}]},request=httpx.Request('POST','https://model.example/chat/completions'))
    monkeypatch.setattr(httpx.Client,'post',post)


def test_model_cannot_return_final_grade_as_authority(monkeypatch):
    model_response(monkeypatch,{'reply':'直接S','project_patch':{},'proposal':None,'grade':'S'})
    with pytest.raises(ValueError): analyze({'base_url':'https://model.example','model':'test'},'',{}, {}, [], [])


def test_model_cannot_patch_company_or_verification(monkeypatch):
    model_response(monkeypatch,{'reply':'建议','project_patch':{'company':{'budget':999999},'verification_status':'verified','target_user':'已说明用户'},'proposal':None})
    r=analyze({'base_url':'https://model.example','model':'test'},'',{}, {}, [], [])
    assert r['project_patch']=={'target_user':'已说明用户'}


def test_model_summary_cannot_replace_original_project_facts(monkeypatch):
    project={'name':'QA5-G01-2-宿迁获客','description':'没有访谈、成交或成本证据；预算20000元'}
    model_response(monkeypatch,{'reply':'待补信息','project_patch':{'name':'宿迁获客','description':'本轮查询宿迁商务统计','budget_requested':20000},'proposal':None})
    r=analyze({'base_url':'https://model.example','model':'test'},'',project,{},[],[])
    reviewed={**project,**r['project_patch']}
    assert reviewed['name']==project['name']
    assert reviewed['description']==project['description']
    assert reviewed['budget_requested']==20000


def test_boolean_score_rejected_before_coercion():
    a=case()[3];a['dimensions']['market']['score']=True
    with pytest.raises(ValueError): validate_proposal(a)


def test_model_malformed_proposal_is_rejected(monkeypatch):
    model_response(monkeypatch,{'reply':'建议','project_patch':{},'proposal':{'dimensions':[]}})
    with pytest.raises(ValueError): analyze({'base_url':'https://model.example','model':'test'},'',{}, {}, [], [])


def test_incomplete_assumptions_repaired_once(monkeypatch):
    from copy import deepcopy
    proposal=case()[3]
    incomplete=deepcopy(proposal)
    incomplete['assumptions']=[]
    for a in proposal['assumptions']:
        a.update(validation_method='负责人核对真实订单',pass_threshold='负责人确认口径后核对',fail_threshold='口径未确认暂停扩量')
    calls=[]
    def post(*args,**kwargs):
        calls.append(deepcopy(kwargs))
        content={'reply':'方向待验证','proposal':incomplete if len(calls)==1 else proposal}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(content)}}]},request=httpx.Request('POST','https://model.example/chat/completions'))
    monkeypatch.setattr(httpx.Client,'post',post)
    r=analyze({'base_url':'https://model.example','model':'test'},'',{}, {}, [], [])
    assert len(calls)==2
    assert r['proposal']['assumptions'][0]['validation_method']=='负责人核对真实订单'
    assert 0<calls[1]['timeout']<=calls[0]['timeout']<=90
    assert len(calls[0]['json']['messages'])==2
    assert len(calls[1]['json']['messages'])==4


@pytest.mark.parametrize('missing',['empty','validation_method','pass_threshold','fail_threshold'])
def test_incomplete_assumptions_never_accepted_after_repair(monkeypatch,missing):
    proposal=case()[3]
    for a in proposal['assumptions']:
        a.update(validation_method='核对订单',pass_threshold='待确认口径',fail_threshold='口径未确认暂停')
    if missing=='empty': proposal['assumptions']=[]
    else: proposal['assumptions'][0][missing]='  '
    calls=[]
    def post(*args,**kwargs):
        calls.append(1)
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'reply':'建议','proposal':proposal})}}]},request=httpx.Request('POST','https://model.example/chat/completions'))
    monkeypatch.setattr(httpx.Client,'post',post)
    with pytest.raises(ValueError,match='缺少完整的关键假设'):
        analyze({'base_url':'https://model.example','model':'test'},'',{}, {}, [], [])
    assert len(calls)==2


@pytest.mark.parametrize('has_proposal',[True,False])
def test_complete_or_no_proposal_does_not_retry(monkeypatch,has_proposal):
    proposal=case()[3] if has_proposal else None
    if proposal:
        for a in proposal['assumptions']:
            a.update(validation_method='核对记录',pass_threshold='待确认口径',fail_threshold='未确认暂停')
    calls=[]
    def post(*args,**kwargs):
        calls.append(1)
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'reply':'建议','proposal':proposal})}}]},request=httpx.Request('POST','https://model.example/chat/completions'))
    monkeypatch.setattr(httpx.Client,'post',post)
    r=analyze({'base_url':'https://model.example','model':'test'},'',{}, {}, [], [])
    assert len(calls)==1
    assert (r['proposal'] is not None)==has_proposal
