import pytest
from tests.test_rating import case
from sabc.rating import assess
from tests.test_app import client


def test_blank_reasons_do_not_count_as_review():
    p,c,e,a=case()
    a['pros']=['','','']; a['cons']=['','','']
    assert assess(p,c,e,a)['grade']=='NR'


def test_unaffordable_test_does_not_recommend_small_test():
    p,c,e,a=case(1)
    c['budget']=0
    result=assess(p,c,e,a)
    assert '暂缓' in result['action']


def test_malformed_proposal_returns_validation_error(client):
    pid=client.post('/api/projects',json={'name':'测试'}).json()['id']
    result=client.post(f'/api/projects/{pid}/assess',json={'proposal':{'dimensions':[]},'confirmed':True})
    assert result.status_code==422


def test_company_confirmation_cannot_be_string(client):
    assert client.put('/api/company',json={'confirmed':'false'}).status_code==422


def test_numeric_project_field_validated(client):
    assert client.post('/api/projects',json={'name':'test','budget_requested':'anything'}).status_code==422


def test_s_conditions_cannot_be_strings(client):
    p,c,e,a=case()
    pid=client.post('/api/projects',json=p).json()['id']
    a['s_conditions']['repeatable']='true'
    assert client.post(f'/api/projects/{pid}/assess',json={'proposal':a,'confirmed':True}).status_code==422
