from copy import deepcopy
from tests.test_rating import case
from tests.test_app import client, as_post
from sabc.rating import assess


def test_superseded_evidence_cannot_keep_old_high_grade():
    p,c,e,a=case()
    e.append({**e[0],'id':'e2','supersedes':'e1','conflict':True,'level':1})
    result=assess(p,c,e,a)
    assert result['grade']=='B'
    assert any('新版本' in w for w in result['warnings'])


def test_reassessment_new_veto_preserves_first_report(client):
    p,c,e,a=case(2)
    client.put('/api/company',json=c)
    pid=client.post('/api/projects',json=p).json()['id']
    as_post(client,pid)
    ev=client.post(f'/api/projects/{pid}/evidence',json=e[0]).json()
    for d in a['dimensions'].values(): d['evidence_ids']=[ev['id']]
    for h in a['assumptions']: h['evidence_ids']=[ev['id']]
    first=client.post(f'/api/projects/{pid}/assess',json={'confirmed':True,'proposal':a}).json()
    negative=client.post(f'/api/projects/{pid}/evidence',json={**e[0],'title':'测试：不可消除的负面事实','content':'测试红线事实，非真实业务'}).json()
    second_proposal=deepcopy(a)
    second_proposal['vetoes']=[{'confirmed':True,'reason':'测试：无现实解决路径','evidence_ids':[negative['id']]}]
    second=client.post(f'/api/projects/{pid}/assess',json={'confirmed':True,'proposal':second_proposal}).json()
    assert first['result']['grade']=='A' and second['result']['grade']=='C'
    assert client.get(f'/api/assessments/{first["id"]}/export').json()['result']['grade']=='A'
