import pytest
from sabc import llm


def test_report_prompt_preserves_rules_without_interview_task(monkeypatch):
    seen = {}
    def capture(client, endpoint, payload, headers, timeout):
        seen['system'] = payload['messages'][0]['content']
        raise RuntimeError('captured before network')
    monkeypatch.setattr(llm, 'completion', capture)
    with pytest.raises(RuntimeError, match='captured before network'):
        llm._analyze({'base_url': 'https://example.com/v1', 'model': 'test'}, 'test',
                     {'_report_requested': True}, {}, [], [])
    prompt = seen['system']
    assert '本轮用户已经点击生成报告' in prompt
    assert '逐维使用正式标准的评分锚点' in prompt
    assert 'B封顶包括' in prompt and '低分校验' in prompt
    assert '没有具体、可描述的潜在否决事实时vetoes必须为空数组' in prompt
    assert '未来可能风险写入assumptions' in prompt
    assert '没有命中时必须为空数组' in prompt
    assert '不能用旧摘要否定conversation中用户后续明确的纠正' in prompt
    assert '暂缓评级：' in prompt and '不编造' in prompt
    assert '访谈正文reply使用正常聊天采访风格' not in prompt
    assert '仍有需要用户回答的问题时' not in prompt
    assert '不追加提问' in prompt or '不再提问' in prompt


def test_model_missing_score_reason_is_format_failure_not_missing_user_fact(monkeypatch):
    import json
    dimensions = {key: {'score': 4, 'basis': 'fact', 'reason': '本项目已有依据'} for key in llm.DIMENSIONS}
    dimensions['risk']['reason'] = '  '
    monkeypatch.setattr(llm, 'completion', lambda *args: json.dumps({
        'reply': '报告已生成。', 'proposal': {'dimensions': dimensions}}))
    with pytest.raises(ValueError, match='评分理由'):
        llm._analyze({'base_url': 'https://example.com/v1', 'model': 'test', 'single_attempt': True},
                     'test', {'_report_requested': True}, {}, [], [])


def test_report_keeps_confirmed_collection_instead_of_model_rewrite(monkeypatch):
    import json
    from copy import deepcopy
    from sabc.lifecycle import initial
    coverage = {k: {'status': 'known', 'reason': '用户已提供判断依据', 'items': {}} for k in llm.DIMENSIONS}
    life = {**initial(), 'mode': 'continuous', 'coverage': coverage}
    project = {'_report_requested': True, 'lifecycle': life}
    before = deepcopy(project)
    proposal = {
        'dimensions': {k: {'score': 4, 'reason': '已有本项目验证记录', 'basis': 'fact'} for k in llm.DIMENSIONS},
        'assumptions': [{'id': 'a', 'claim': '效果持续', 'validation_method': '按月核对',
                         'pass_threshold': '保持当前效果', 'fail_threshold': '不再保持效果'}],
        'pros': ['需求', '资源', '现金'], 'cons': ['效果变化', '费用变化', '人员变化']}
    monkeypatch.setattr(llm, 'completion', lambda *args: json.dumps({
        'reply': '报告已生成。', 'proposal': proposal,
        'dimension_coverage': {k: 'ask' for k in llm.DIMENSIONS},
        'stage_review': {'conclusion': 'continue', 'summary': '按当前范围评估', 'next_action': '按月核对'}}))
    result = llm._analyze({'base_url': 'https://example.com/v1', 'model': 'test'}, 'test', project, {}, [], [])
    assert result['dimension_coverage'] == coverage
    assert project == before


@pytest.mark.parametrize('section', ['dimensions', 'assumptions', 'vetoes'])
def test_report_rejects_invented_evidence_reference(monkeypatch, section):
    import json
    proposal = {
        'dimensions': {k: {'score': 4, 'reason': '本项目已有记录', 'basis': 'fact'} for k in llm.DIMENSIONS},
        'assumptions': [{'id': 'a', 'claim': '效果持续', 'validation_method': '按月核对',
                         'pass_threshold': '保持效果', 'fail_threshold': '效果下降'}],
        'vetoes': []}
    if section == 'dimensions':
        proposal[section]['risk']['evidence_ids'] = ['record-typo']
    elif section == 'assumptions':
        proposal[section][0]['evidence_ids'] = ['record-typo']
    else:
        proposal[section] = [{'reason': '具体潜在红线', 'confirmed': False, 'evidence_ids': ['record-typo']}]
    monkeypatch.setattr(llm, 'completion', lambda *args: json.dumps({'reply': '报告已生成。', 'proposal': proposal}))
    with pytest.raises(ValueError, match='不存在的证据ID'):
        llm._analyze({'base_url': 'https://example.com/v1', 'model': 'test', 'single_attempt': True},
                     'test', {'_report_requested': True}, {}, [{'id': 'record-real'}], [])
