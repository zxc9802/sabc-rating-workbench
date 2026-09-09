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


def test_boolean_score_rejected_before_coercion():
    a=case()[3];a['dimensions']['market']['score']=True
    with pytest.raises(ValueError): validate_proposal(a)


def test_model_malformed_proposal_is_rejected(monkeypatch):
    model_response(monkeypatch,{'reply':'建议','project_patch':{},'proposal':{'dimensions':[]}})
    with pytest.raises(ValueError): analyze({'base_url':'https://model.example','model':'test'},'',{}, {}, [], [])
