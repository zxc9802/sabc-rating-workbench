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
    with pytest.raises(ValueError): analyze({'base_url':'https://model.example','model':'test'},'',{'_report_requested': True}, {}, [], [])


def test_model_cannot_patch_company_or_verification(monkeypatch):
    model_response(monkeypatch,{'reply':'建议','project_patch':{'company':{'budget':999999},'verification_status':'verified','target_user':'已说明用户'},'proposal':None})
    r=analyze({'base_url':'https://model.example','model':'test'},'',{'_report_requested': True}, {}, [], [])
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
    with pytest.raises(ValueError): analyze({'base_url':'https://model.example','model':'test'},'',{'_report_requested': True}, {}, [], [])


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
    r=analyze({'base_url':'https://model.example','model':'test'},'',{'_report_requested': True}, {}, case()[2], [])
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
        analyze({'base_url':'https://model.example','model':'test'},'',{'_report_requested': True}, {}, case()[2], [])
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
    r=analyze({'base_url':'https://model.example','model':'test'},'',{'_report_requested': True}, {}, case()[2], [])
    assert len(calls)==1
    assert (r['proposal'] is not None)==has_proposal


@pytest.mark.parametrize('invalid',[
    {'reply':'方向待验证','proposal':{'dimensions':[]}},
    {'reply':'方向待验证','proposal':{'assumptions':[{'claim':'需求待验证'}]}},
    {'reply':'方向待验证','questions':['问题一','问题二','问题三']},
])
def test_structural_error_is_repaired_without_accepting_invalid_proposal(monkeypatch,invalid):
    calls=[]
    def post(*args,**kwargs):
        calls.append(kwargs['timeout'])
        content=invalid if len(calls)==1 else {'reply':'还需核实需求。','proposal':None}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(content)}}]},request=httpx.Request('POST','https://model.example/chat/completions'))
    monkeypatch.setattr(httpx.Client,'post',post)
    result=analyze({'base_url':'https://model.example','model':'test'},'',{'_report_requested': True}, {}, [], [])
    assert result['proposal'] is None
    assert result['reply']=='还需核实需求。'
    assert len(calls)==2 and 0<calls[1]<=calls[0]<=90


def test_ordinary_interview_does_not_accept_unsolicited_scoring(monkeypatch):
    model_response(monkeypatch, {'reply': '资料已梳理，请选择生成报告或继续补充。', 'project_patch': {},
                                'proposal': {'dimensions': []},
                                'stage_review': {'conclusion': 'trial', 'summary': '提前评价', 'next_action': '试点'}})
    result = analyze({'base_url': 'https://model.example', 'model': 'test'}, '', {}, {}, [], [])
    assert result['proposal'] is None
    assert result['stage_review'] is None


def test_completed_collection_does_not_request_or_return_report(monkeypatch):
    from tests.report_fixtures import draft_reply
    from sabc.lifecycle import initial
    calls=[]
    reply=draft_reply();reply.pop('mode')
    def post(*args,**kwargs):
        calls.append(kwargs['json'])
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(reply)}}]},request=httpx.Request('POST','https://model.example/chat/completions'))
    monkeypatch.setattr(httpx.Client,'post',post)
    project={'_prepare_report':True,'lifecycle':initial()}
    result=analyze({'base_url':'https://model.example','model':'test'},'',project,{},[],[])
    assert len(calls)==1
    assert result['proposal'] is None and result['stage_review'] is None
    prompt=calls[0]['messages'][0]['content']
    assert '仅整理事实与八维覆盖状态，不生成或预备评分草稿' in prompt
    assert '本轮生成报告，proposal结构' not in prompt


def test_explicit_report_requires_scoring_and_advice(monkeypatch):
    from sabc.lifecycle import initial, DIMENSIONS
    model_response(monkeypatch,{'reply':'信息已整理完成，现在生成报告吗？','dimension_coverage':{key:{'status':'known','reason':'已提供'} for key in DIMENSIONS}})
    with pytest.raises(ValueError,match='报告必须包含完整评分和建议'):
        analyze({'base_url':'https://model.example','model':'test'},'',{'_report_requested':True,'lifecycle':initial()}, {}, [], [])
