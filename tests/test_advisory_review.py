from copy import deepcopy
import json
import httpx
import pytest

from tests.test_app import client
from tests.test_rating import case
from sabc import lifecycle
from sabc.llm import review_report
from sabc.streaming import progress


def draft_reply():
    proposal = case()[3]
    for item in proposal['assumptions']:
        item.update(validation_method='核对原始记录', pass_threshold='收入覆盖全部成本', fail_threshold='达到损失上限停止')
    return {'mode': 'model', 'reply': '正在整理判断', 'project_patch': {}, 'questions': [],
            'proposal': proposal, 'dimension_coverage': {
                key: {'status': 'known', 'reason': '已提供具体判断依据'} for key in lifecycle.DIMENSIONS},
            'stage_review': {'conclusion': 'trial', 'summary': '值得小额验证', 'next_action': '核对完整成本', 'next_review_days': 14}}


@pytest.mark.parametrize('outcome', ['revise', 'ask', 'failure'])
def test_review_controls_report_save_and_preserves_audit(client, monkeypatch, outcome):
    import sabc.app as module
    p, c, _, _ = case()
    client.put('/api/company', json=c)
    project = client.post('/api/projects', json=p).json()
    project['lifecycle']['coverage'] = draft_reply()['dimension_coverage']
    module.store.save('projects', project)
    monkeypatch.setattr(module, 'settings', lambda: {'base_url': 'https://model.example', 'model': 'test'})
    monkeypatch.setattr(module, 'analyze', lambda *args: draft_reply())
    def review(*args):
        if outcome == 'failure':
            raise ValueError('复核未完成，请重试')
        answer = deepcopy(args[-1])
        answer['review_notes'] = [{'perspective': k, 'finding': '对照已有事实复核', 'evidence_ids': []} for k in ('value', 'execution', 'risk')]
        if outcome == 'ask':
            answer.update(reply='退出时能收回多少押金？', questions=['退出时能收回多少押金？'], proposal=None, stage_review=None)
            answer['dimension_coverage']['cash'] = {'status': 'ask', 'reason': '退出损失尚可询问'}
        else:
            answer['proposal']['dimensions']['return'].update(score=0, reason='已知完整成本超过回报', basis='fact')
        return answer
    monkeypatch.setattr(module, 'review_report', review)
    url = f"/api/projects/{project['id']}"
    response = client.post(url + '/chat', json={'message': '最后一条访谈信息'})
    detail = client.get(url).json()
    if outcome == 'failure':
        assert response.status_code == 422
        assert detail['assessments'] == []
        assert not detail['project'].get('proposal')
    elif outcome == 'ask':
        assert response.status_code == 200
        assert detail['assessments'] == []
        assert detail['project']['interview']['state'] == 'gathering'
        assert detail['project']['messages'][-1]['content'] == '退出时能收回多少押金？'
        assert detail['project']['assessment_review']['questions']
    else:
        assert detail['assessments'] == []
        assert detail['project']['report_ready']
        assert client.post(url + '/chat', json={'message':'生成报告','generate_report':True}).json()['report_id']
        report = client.get(url).json()['assessments'][0]
        assert report['result']['base_score'] == 80
        audit = report['snapshot']['project']['assessment_review']
        assert audit['draft_proposal']['dimensions']['return']['score'] == 5
        assert audit['revised_proposal']['dimensions']['return']['score'] == 0
        assert len(audit['notes']) == 3


@pytest.mark.parametrize('invalid', [None, 'facts', 'evidence', 'missing_view', 'unasked_gap'])
def test_independent_review_contract_and_hidden_stream(monkeypatch, invalid):
    p, c, evidence, _ = case()
    p['lifecycle'] = {**lifecycle.initial(), 'mode': 'continuous'}
    draft = draft_reply()
    answer = {k: v for k, v in draft.items() if k != 'mode'}
    answer['review_notes'] = [{'perspective': k, 'finding': '依据已提供资料核对', 'evidence_ids': ['e1']} for k in ('value', 'execution', 'risk')]
    if invalid == 'facts': answer['project_patch'] = {'budget_requested': 99999}
    if invalid == 'evidence': answer['proposal']['dimensions']['market']['evidence_ids'] = ['invented']
    if invalid == 'missing_view': answer['review_notes'][2]['perspective'] = 'value'
    if invalid == 'unasked_gap': answer['dimension_coverage']['cash']['status'] = 'ask'
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs['json'])
        assert progress.get() is None
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(answer)}}]}, request=httpx.Request('POST', 'https://model.example/chat/completions'))
    monkeypatch.setattr(httpx.Client, 'post', post)
    monkeypatch.delenv('SABC_DEEPSEEK_API_KEY', raising=False)
    notify = lambda text: None
    token = progress.set(notify)
    try:
        if invalid:
            with pytest.raises(ValueError):
                review_report({'base_url': 'https://model.example', 'model': 'test'}, '', p, c, evidence, [], draft)
        else:
            result = review_report({'base_url': 'https://model.example', 'model': 'test'}, '', p, c, evidence, [], draft)
            assert result['proposal']
            assert len(calls) == 1
            context = json.loads(calls[0]['messages'][1]['content'])
            assert context['draft_to_review']['proposal'] == draft['proposal']
            assert context['facts']['company'] == c
        assert progress.get() is notify
    finally:
        progress.reset(token)
