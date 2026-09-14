"""Regressions from the commercial SaaS online interview on 2026-09-14."""
from copy import deepcopy

import pytest

from sabc import advisory, checkpoints
from tests.test_checkpoints import result
from tests.test_hidden_review import accepted
from tests.test_rating import case
from tests.test_app import client
from sabc.fact_boundaries import qualification, gap_details


def test_unknown_answer_closes_the_question_even_when_model_omits_it():
    p = {'framing': {'purpose': 'research'}, 'messages': [
        {'role': 'assistant', 'content': '运营方最多能承受多少不可回收损失？',
         'question_targets': ['cash.max_loss']} ]}
    r = result()
    r.update(reply='亏到多少必须停止？', questions=['亏到多少必须停止？'],
             question_targets=['cash.max_loss'])
    answer = '运营方最多能承受多少不可回收损失：不知道，无法提供。我的个人研究现金损失上限0元。'
    checkpoints.normalize(r, p, {}, [], p['messages'] + [{'role': 'user', 'content': answer}])
    item = r['dimension_coverage']['cash']['items']['max_loss']
    assert item['status'] == 'unknown'
    assert '不知道' in item['quote']
    assert 'cash.max_loss' not in r['question_targets']
    assert '亏到多少' not in r['reply']


def test_short_unknown_is_bound_to_the_single_previous_question():
    p = {'messages': [{'role': 'assistant', 'content': '最大损失承受额是多少？',
                       'question_targets': ['cash.max_loss']}]}
    r = checkpoints.normalize(result(), p, {}, [], p['messages'] + [{'role': 'user', 'content': '不知道'}])
    assert r['dimension_coverage']['cash']['items']['max_loss']['status'] == 'unknown'
    assert r['dimension_coverage']['cash']['items']['investment_limit']['status'] == 'ask'


def test_unrelated_latest_quote_cannot_reopen_answered_report_purpose():
    quote = '报告只供我自己做行业研究归档，不发布，不作为采购或投资建议。'
    prior = {'status': 'known', 'source': 'user', 'quote': quote, 'verified': True}
    p = {'messages': [{'role': 'user', 'content': quote}],
         'lifecycle': {'coverage': {'strategy': {'items': {'purpose': prior}}}}}
    latest = '不做或延后一个月，只是晚形成个人认识，不影响现有经营。'
    r = result()
    r['dimension_coverage']['strategy']['items'] = {
        'purpose': {'status': 'ask', 'source': 'user', 'quote': latest}}
    r.update(reply='报告个人归档还是对外引用？', questions=['报告个人归档还是对外引用？'],
             question_targets=['strategy.purpose'])
    checkpoints.normalize(r, p, {}, [], [{'role': 'user', 'content': latest}])
    assert r['dimension_coverage']['strategy']['items']['purpose']['status'] == 'known'
    assert 'strategy.purpose' not in r['question_targets']
    assert '对外引用' not in r['reply']


@pytest.mark.parametrize('targets', [[], ['cash.max_loss', 'strategy.purpose'], ['bogus.field']])
def test_questions_without_valid_bindings_are_replaced_with_pending_questions(targets):
    quote = '最多能承受的损失未知'
    p = {'description': quote, 'lifecycle': {'coverage': {'cash': {'items': {
        'max_loss': {'status': 'unknown', 'source': 'user', 'quote': quote, 'verified': True}}}}}}
    r = result()
    r.update(reply='最多能承受多少不可回收损失？', questions=['最多能承受多少不可回收损失？'],
             question_targets=targets)
    checkpoints.normalize(r, p, {}, [], [])
    assert '损失' not in r['reply']
    assert len(r['question_targets']) == len(r['questions']) > 0
    for target in r['question_targets']:
        dim, key = target.split('.')
        assert r['dimension_coverage'][dim]['items'][key]['status'] == 'ask'


def test_missing_records_are_not_interpreted_as_no_test_history():
    quote = '我没有实测记录，也不了解运营方是否做过试点。'
    assert not checkpoints.no_test(quote)


def test_explicit_no_trial_is_preserved_even_when_results_are_unknown():
    quote = '本项目没做过试点，效果未知。'
    assert checkpoints.no_test(quote)


@pytest.mark.parametrize('model_marks_both_answered', [False, True])
def test_short_unknown_after_two_questions_does_not_close_both(model_marks_both_answered):
    p = {'messages': [{'role': 'assistant', 'content': '总预算是多少？最大损失是多少？',
                       'question_targets': ['cash.investment_limit', 'cash.max_loss']}]}
    r = result()
    if model_marks_both_answered:
        r['dimension_coverage']['cash']['items'] = {key: {'status': 'unknown', 'source': 'user', 'quote': '不知道'}
            for key in ('investment_limit', 'max_loss')}
    checkpoints.normalize(r, p, {}, [], p['messages'] + [{'role': 'user', 'content': '不知道'}])
    assert all(r['dimension_coverage']['cash']['items'][key]['status'] == 'ask'
               for key in ('investment_limit', 'max_loss'))


@pytest.mark.parametrize('quote', ['0元', '现金损失上限0元'])
def test_short_researcher_quote_cannot_be_used_as_operator_limit(quote):
    p = {'framing': {'purpose': 'research'}, 'messages': [
        {'role': 'assistant', 'content': '运营方能承受的最大损失是多少？', 'question_targets': ['cash.max_loss']}]}
    r = result()
    r['dimension_coverage']['cash']['items'] = {'max_loss': {
        'status': 'known', 'source': 'user', 'quote': quote, 'subject': 'operator'}}
    checkpoints.normalize(r, p, {}, [], p['messages'] + [
        {'role': 'user', 'content': '我的个人研究现金损失上限0元。'}])
    assert r['dimension_coverage']['cash']['items']['max_loss']['status'] == 'ask'


def test_new_records_replace_previous_unavailable_answer():
    quote = '我未取得实测记录'
    prior = {'status': 'unknown', 'source': 'user', 'quote': quote, 'verified': True}
    p = {'description': quote, 'lifecycle': {'coverage': {'return': {'items': {'validation_records': prior}}}}}
    new = '现在已取得运营方测试日志，由财务张三核对'
    r = result()
    r['dimension_coverage']['return']['items'] = {'validation_records': {
        'status': 'known', 'source': 'user', 'quote': new}}
    checkpoints.normalize(r, p, {}, [], [{'role': 'user', 'content': new}])
    item = r['dimension_coverage']['return']['items']['validation_records']
    assert item['status'] == 'known' and item['quote'] == new
    assert item['knowledge'] == 'reported'


def test_rejected_question_keeps_uploaded_material_explanation():
    quote = '最大损失未知'
    p = {'description': quote, 'lifecycle': {'coverage': {'cash': {'items': {
        'max_loss': {'status': 'unknown', 'source': 'user', 'quote': quote, 'verified': True}}}}}}
    r = result()
    r.update(reply='附件描述了两个使用场景，尚不能证明实际收益。\n最大损失是多少？',
             questions=['最大损失是多少？'], question_targets=['cash.max_loss'])
    checkpoints.normalize(r, p, {}, [], [])
    assert '附件描述了两个使用场景' in r['reply']
    assert '最大损失是多少' not in r['reply']


def test_gap_summary_is_bounded_without_truncating_away_qualifiers():
    sources = []
    coverage = {}
    for dim, checks in checkpoints.CHECKS.items():
        items = {}
        for key in checks:
            quote = dim + key + '相关背景' * 150 + '，我未取得相关资料'
            sources.append({'role': 'user', 'content': quote})
            items[key] = {'status': 'unknown', 'source': 'user', 'quote': quote, 'verified': True}
        coverage[dim] = {'status': 'unknown', 'items': items}
    details = '\n'.join(gap_details({'messages': sources, 'lifecycle': {'coverage': coverage}}))
    assert len(details) < 3000
    assert '本次未取得相关资料' in details


@pytest.mark.parametrize('claim', ['本项目无实测记录。', '运营方没有合规授权。'])
def test_review_rejects_absolute_absence_without_matching_negative_evidence(claim):
    p, c, e, _ = case()
    quote = '我尚未取得运营方实测记录，也不了解合规授权情况。'
    p.update(description=quote, lifecycle={'coverage': {'risk': {
        'status': 'external', 'reason': claim, 'items': {'compliance': {
            'source': 'user', 'status': 'external', 'quote': quote, 'verified': True}}}}})
    context = advisory.packet('collection', p, c, e, None)
    with pytest.raises(ValueError, match='未知|未取得|不存在|限定'):
        advisory.validate(accepted(), context)


def test_nr_summary_uses_original_evidence_limits_instead_of_model_paraphrase():
    import sabc.app as module
    p, c, e, proposal = case()
    p['id'] = 'boundary-summary'
    proposal['dimensions']['return'].update(score=None, basis='unknown')
    quote = '我尚未取得运营方实测记录，也不了解合规授权情况。'
    p.update(description=quote, framing={'purpose': 'research'}, lifecycle={
        'stage': 'pre',
        'coverage': {'return': {'status': 'unknown', 'reason': '本项目无实测记录，也无合规授权。',
            'items': {'validation_records': {'status': 'unknown', 'source': 'user',
                                              'quote': quote, 'verified': True}}}},
        'review': {'conclusion': 'needs_info', 'summary': '错误摘要', 'next_action': '待核查'}})
    report = module.build_assessment(p, c, e, deepcopy(proposal))
    summary = report['result']['deferral_reason']
    assert '本项目无实测记录' not in summary and '无合规授权' not in summary
    assert '尚未取得' in summary
    assert quote in summary
    assert report['snapshot']['project']['lifecycle']['review']['summary'] == summary


def test_report_correction_can_replace_the_same_error_in_derived_result():
    import sabc.app as module
    from tests.report_fixtures import draft_reply
    p, c, e, _ = case()
    quote = '我未取得运营方的合规授权资料'
    p.update(id='corrected-boundary', description=quote, lifecycle={'stage': 'pre', 'coverage': {'risk': {
        'status': 'unknown', 'reason': '授权情况待核查', 'items': {'compliance': {
            'status': 'unknown', 'source': 'user', 'quote': quote, 'verified': True}}}}})
    proposal = draft_reply()['proposal']
    proposal['cons'][0] = '运营方没有合规授权。'
    candidate = module.build_assessment(p, c, e, proposal)
    context = advisory.packet('report', p, c, e, candidate)
    with pytest.raises(ValueError, match='客观不存在'):
        advisory.validate(accepted(), context)
    corrected = deepcopy(proposal)
    corrected['cons'][0] = '尚未取得合规授权资料，不能据此判断是否合规。'
    response = accepted()
    response.update(proposal=corrected, checks={**response['checks'], 'facts': 'revise'},
        stage_review={'conclusion': 'needs_info', 'summary': '授权情况待核查', 'next_action': '获取经授权的资料'},
        findings=[{'perspective': 'facts', 'target': 'candidate.proposal.cons.0',
                   'source_id': 'description', 'quote': quote, 'reason': '将未取得资料误写成没有授权'}])
    validated = advisory.validate(response, context)
    assert validated['proposal']['cons'][0] == corrected['cons'][0]
    # Guard-only coverage must not leak into the strict StageReview output schema.
    from sabc.lifecycle import StageReview
    assert StageReview.model_validate(validated['stage_review']).summary == '授权情况待核查'


def test_actual_reported_absence_is_not_erased_by_an_unrelated_missing_record():
    coverage = {'risk': {'reason': '运营方没有合规授权。', 'items': {
        'compliance': {'source': 'user', 'quote': '运营方没有合规授权'},
        'control': {'source': 'user', 'quote': '我未取得运营方的实测记录和授权书'}}}}
    assert advisory.source_limit_flags(coverage) == []


def test_chat_persists_question_binding_and_blocks_repeat_without_extra_call(client, monkeypatch):
    import json
    import sabc.app as module
    from sabc import llm
    pid = client.post('/api/projects', json={'name': '问题绑定回归', 'description': '商业产品外部研究'}).json()['id']
    monkeypatch.setattr(module, 'settings', lambda: {'base_url': 'https://model.example', 'model': 'test'})
    monkeypatch.setattr(module.planner, 'configured', lambda: False)
    monkeypatch.setattr(module, 'analyze', llm._analyze)
    raw = result()
    raw.update(reply='最多能承受多少不可回收损失？', questions=['最多能承受多少不可回收损失？'],
               question_targets=['cash.max_loss'])
    calls = []
    def completion(*args):
        calls.append(True)
        return json.dumps(raw, ensure_ascii=False)
    monkeypatch.setattr(llm, 'completion', completion)
    url = f'/api/projects/{pid}'
    assert client.post(url + '/chat', json={'message': '先了解项目情况'}).status_code == 200
    p = client.get(url).json()['project']
    assert p['messages'][-1]['question_targets'] == p['interview']['question_targets'] == ['cash.max_loss']
    response = client.post(url + '/chat', json={'message': '不知道'})
    assert response.status_code == 200
    p = client.get(url).json()['project']
    assert 'cash.max_loss' not in p['interview']['question_targets']
    assert p['lifecycle']['coverage']['cash']['items']['max_loss']['knowledge'] == 'unknown'
    assert len(calls) == 2


@pytest.mark.parametrize('quote,kind', [
    ('我没有实测记录', 'not_obtained'),
    ('公司没有向我们提供具体追加方案、预算、目标值和负责人', 'not_obtained'),
    ('我未拿到授权书', 'not_obtained'),
    ('运营方是否取得合规授权，我不知道', 'unknown'),
    ('运营方没有合规授权', 'reported_absent'),
])
def test_source_qualifications_keep_the_distinction(quote, kind):
    assert qualification(quote, 'unknown')['knowledge'] == kind
