from copy import deepcopy

from tests.test_app import client
from tests.test_report_generation import prepare, send


def test_revision_reuses_original_sources_and_keeps_previous_snapshot(client, monkeypatch):
    module, advisory, url, calls = prepare(client, monkeypatch)
    assert send(client, url).status_code == 200
    first = deepcopy(client.get(url).json()['assessments'][0])
    pid = url.split('/')[-1]
    module.store.save('report_turns', {'id':'question-1','project_id':pid,'assessment_id':first['id'],
                                     'question':'现金依据是不是用了集团口径？','reply':'应核对原始资料，不是经营事实。'})
    captured = []
    original = module.analyze
    def analyze(*args):
        captured.append(deepcopy(args[2]))
        result=original(*args)
        result['proposal']['cons'][0]='仍需核查单位经济的成本边界'
        return result
    monkeypatch.setattr(module, 'analyze', analyze)
    body = {'message':'根据问题修订','generate_report':True,'revision_of':first['id'],'revision_turn_id':'question-1'}
    revised = client.post(url+'/chat', json=body)
    assert revised.status_code == 200, revised.text
    second = client.get(url).json()['assessments'][0]
    assert second['id'] != first['id']
    assert second['result']['revision']['source_report_id'] == first['id']
    assert '反方结论' in second['result']['revision']['changes']
    assert client.get('/api/assessments/'+first['id']+'/export').json() == first
    assert captured[0]['report_revision']['question'] == '现金依据是不是用了集团口径？'
    assert all(m['content'] != '应核对原始资料，不是经营事实。' for m in captured[0]['messages'])
    assert client.post(url+'/chat', json=body).json()['report_id'] == second['id']
    assert len(client.get(url).json()['assessments']) == 2


def test_revision_rejects_question_from_another_report(client, monkeypatch):
    module, _, url, _ = prepare(client, monkeypatch)
    send(client, url)
    report = client.get(url).json()['assessments'][0]
    module.store.save('report_turns', {'id':'foreign','project_id':url.split('/')[-1],
        'assessment_id':'other-report','question':'其他报告的问题','reply':'回答'})
    response = client.post(url+'/chat', json={'message':'修订','generate_report':True,
        'revision_of':report['id'],'revision_turn_id':'foreign'})
    assert response.status_code == 422
    assert len(client.get(url).json()['assessments']) == 1
