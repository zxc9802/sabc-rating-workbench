"""访谈内完成对抗性审查后，生成报告入口只做确定性计算。

覆盖真实 HTTP 路由与任务队列（含 chat 端点的流式进度回调），
补充只调用 chat_turn 的单测无法触及的路径。
"""
from copy import deepcopy

from tests.test_app import client
from tests.test_rating import case
from sabc import lifecycle


def draft_reply():
    proposal = deepcopy(case()[3])
    for item in proposal['assumptions']:
        item.update(validation_method='核对原始记录', pass_threshold='收入覆盖全部成本', fail_threshold='达到损失上限停止')
    return {'mode': 'model', 'reply': '正在整理判断', 'project_patch': {}, 'questions': [],
            'proposal': proposal, 'dimension_coverage': {
                key: {'status': 'known', 'reason': '已提供具体判断依据'} for key in lifecycle.DIMENSIONS},
            'stage_review': {'conclusion': 'trial', 'summary': '值得小额验证', 'next_action': '核对完整成本', 'next_review_days': 14}}


def asked_reply(draft):
    answer = deepcopy(draft)
    answer.update(reply='退出时能收回多少押金？', questions=['退出时能收回多少押金？'], proposal=None, stage_review=None)
    answer['dimension_coverage']['cash'] = {'status': 'ask', 'reason': '退出损失尚可询问'}
    return answer


def reviewed_reply(draft, ask=False):
    if ask:
        return asked_reply(draft)
    answer = deepcopy(draft)
    answer['review_notes'] = [{'perspective': k, 'finding': '对照已有事实复核', 'evidence_ids': []} for k in ('value', 'execution', 'risk')]
    return answer


def prepare(client, monkeypatch, calls, script=None):
    """script 按轮次给出每轮答复类型：draft（完整判断）或 ask（重新出现可答缺口）。"""
    import sabc.app as module
    script = script or ['draft']
    p, c, _, _ = case()
    client.put('/api/company', json=c)
    project = client.post('/api/projects', json=p).json()
    project['lifecycle']['coverage'] = draft_reply()['dimension_coverage']
    module.store.save('projects', project)
    monkeypatch.setattr(module, 'settings', lambda: {'base_url': 'https://model.example', 'model': 'test'})

    turns = {'n': 0}

    def step():
        return script[min(turns['n'], len(script) - 1)]

    def analyze(settings, key, project, *rest):
        kind = step()
        turns['n'] += 1
        calls.append('analyze')
        draft = draft_reply()
        return asked_reply(draft) if kind == 'ask' else draft

    def review(settings, key, project, *rest):
        kind = script[min(turns['n'] - 1, len(script) - 1)]
        calls.append('review')
        return reviewed_reply(rest[-1], ask=kind == 'ask')

    monkeypatch.setattr(module, 'analyze', analyze)
    monkeypatch.setattr(module, 'review_report', review)
    return f"/api/projects/{project['id']}"


def test_closing_turn_reviews_before_the_generate_entry_appears(client, monkeypatch):
    calls = []
    url = prepare(client, monkeypatch, calls)
    closing = client.post(url + '/chat', json={'message': '最后一条访谈信息'})
    assert closing.status_code == 200
    assert calls == ['analyze', 'review']
    detail = client.get(url).json()
    # 审查在访谈内完成，报告尚未保存，生成入口只等用户点击。
    assert detail['project']['review_complete'] is True
    assert detail['project']['report_ready'] is True
    assert detail['assessments'] == []
    assert detail['project']['assessment_review']['approved'] is True


def test_generate_action_never_calls_the_model_again(client, monkeypatch):
    calls = []
    url = prepare(client, monkeypatch, calls)
    client.post(url + '/chat', json={'message': '最后一条访谈信息'})
    generated = client.post(url + '/chat', json={'message': '生成报告', 'generate_report': True}).json()
    assert generated['report_id']
    assert calls == ['analyze', 'review']
    detail = client.get(url).json()
    assert [r['id'] for r in detail['assessments']] == [generated['report_id']]


def test_queued_generate_job_keeps_the_progress_stream(client, monkeypatch):
    from uuid import uuid4
    import time
    calls = []
    url = prepare(client, monkeypatch, calls)
    client.post(url + '/chat', json={'message': '最后一条访谈信息'})
    submitted = client.post(url + '/jobs', json={'id': str(uuid4()), 'operation': 'chat',
                                                 'payload': {'message': '生成报告', 'generate_report': True}})
    assert submitted.status_code == 202
    # 排队期间前端据此显示“正在生成报告…”，刷新后仍要能区分这个任务。
    assert submitted.json()['generate_report'] is True
    ident = submitted.json()['id']
    for _ in range(100):
        job = client.get('/api/jobs/' + ident).json()
        if job['status'] != 'running':
            break
        time.sleep(0.05)
    assert job['generate_report'] is True
    assert job['status'] == 'success'
    assert job['result']['report_id']
    assert calls == ['analyze', 'review']
    assert client.get(url).json()['project']['report_ready'] is True


def test_new_interview_input_revokes_the_review(client, monkeypatch):
    calls = []
    url = prepare(client, monkeypatch, calls, script=['draft', 'ask'])
    client.post(url + '/chat', json={'message': '最后一条访谈信息'})
    assert client.get(url).json()['project']['report_ready'] is True
    # 审查后再次补充信息并重新出现可答缺口，旧授权必须失效。
    client.post(url + '/chat', json={'message': '补充一条新情况'})
    detail = client.get(url).json()
    assert detail['project']['report_ready'] is False
    assert detail['project']['review_complete'] is False
    calls.clear()
    blocked = client.post(url + '/chat', json={'message': '生成报告', 'generate_report': True}).json()
    assert blocked.get('needs_review') or blocked.get('needs_fact_confirmation')
    assert calls == []
    assert client.get(url).json()['assessments'] == []
