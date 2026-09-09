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
