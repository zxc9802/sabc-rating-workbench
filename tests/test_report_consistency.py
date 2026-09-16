"""Regressions from the September 16 report revision, plus boundary counterexamples."""
from copy import deepcopy
import json

import pytest

from sabc import advisory, llm, report_grounding, report_inputs
from sabc.context import model_context
from sabc.report_corrections import ReportCorrections
from sabc.standard import ground_low_scores, reconcile_unknown_scores
from sabc.fact_boundaries import unsupported_absence
from tests.report_fixtures import grounded_proposal, REPORT_DESCRIPTION
from tests.test_report_timeouts import report_input
from tests.test_rating import case


WORKLOAD = '两位运营合计每月约核对120份商品资料，初次核对约30小时，返工约10小时，合计40小时；只是估计，还没有计时记录。'
SCOPE = '先覆盖当前中文规格资料，跨语言或跨品类不在这次申请范围。'


def test_revision_uses_current_gap_and_synchronizes_withheld_score():
    from sabc.app import build_assessment
    p, c, e, _ = case()
    stale = '跨语言、跨品类需要多少额外投入完全未知，既没有报价也没有迁移测试'
    p.update(id='synthetic-revision', description=REPORT_DESCRIPTION,
             messages=[{'role': 'user', 'content': stale}, {'role': 'user', 'content': SCOPE}],
             lifecycle={'stage': 'pre', 'coverage': {'replication': {'status': 'unknown', 'items': {
                 'extra_investment': {'status': 'unknown', 'source': 'user', 'quote': stale, 'verified': True}}}},
                 'review': {'conclusion': 'needs_info', 'summary': stale, 'next_action': '补资料'}})
    proposal = grounded_proposal()
    dim = proposal['dimensions']['replication']
    dim.update(score=2.5, anchor_score=2, basis='fact', negative_fact='', support=[],
               reason='接手效果尚未测试，这些缺口使复制只能给到2.5分。',
               missing_evidence='缺少另一位普通运营按文档独立接手的实际记录。')
    before = deepcopy(p)
    ground_low_scores(proposal, p, c, e, p['messages'])
    report = build_assessment(p, c, e, proposal)
    saved = report['snapshot']['proposal']['dimensions']['replication']
    assert saved['score'] is None and saved['anchor_score'] is None
    assert '2.5分' not in saved['reason'] and '独立接手' in saved['reason']
    summary = report['result']['deferral_reason']
    assert '独立接手' in summary and '跨语言' not in summary
    assert report['snapshot']['project']['lifecycle']['review']['summary'] == summary
    assert p == before  # Correcting a report never edits the original history.
    assert report['result']['grade'] == 'NR'


def test_unknown_normalization_does_not_rewrite_source_quotes_or_business_minutes():
    proposal = {'dimensions': {'cash': {'score': None, 'anchor_score': 3, 'basis': 'unknown',
        'reason': '每份处理5分钟的目标仍待验证。', 'support': [{'quote': '希望每份5分钟'}]}}}
    reconcile_unknown_scores(proposal)
    dim = proposal['dimensions']['cash']
    assert dim['anchor_score'] is None and dim['reason'] == '每份处理5分钟的目标仍待验证。'
    assert dim['support'] == [{'quote': '希望每份5分钟'}]


def test_review_does_not_cross_apply_expansion_unknown_to_current_test_history():
    coverage = {
        'replication': {'reason': '范围之外的推广成本未知', 'items': {'expansion': {
            'quote': '跨语言、跨品类需要多少额外投入完全未知，既没有报价也没有迁移测试'}}},
        'risk': {'reason': '漏报误报率尚无实测，数据权限依赖主管落实', 'items': {'history': {
            'quote': '本项目没有做过测试、试点或实际运行'}}},
    }
    candidate = {'review': {'summary': '当前方案仍待验证', 'coverage': deepcopy(coverage)}}
    assert advisory.source_limit_flags(coverage, candidate) == []
    # An actual same-dimension loss of a source qualifier remains an error.
    coverage['risk']['items']['history']['quote'] = '我尚未取得本项目的实测记录'
    flags = advisory.source_limit_flags(coverage, candidate)
    assert any(f['target'] == 'coverage.risk.reason' for f in flags)


@pytest.mark.parametrize('claim', [
    '新流程能否实现净释放8小时完全缺乏实测依据（待验证）',
    '计划中的20份人工基线与80份影子测试均为将来安排，本项目尚未开展测试，因此新流程尚无实测依据。',
])
def test_missing_support_is_not_misread_as_confirmed_absence(claim):
    limits = ['跨语言、跨品类需要多少额外投入完全未知，既没有报价也没有迁移测试']
    assert list(unsupported_absence(claim, limits)) == []


def test_evidence_qualification_does_not_hide_another_absolute_claim():
    flags = list(unsupported_absence('缺少实测依据，而且运营方没有合规授权。', ['尚未取得合规授权资料']))
    assert len(flags) == 1 and '没有合规授权' in flags[0][0]


def test_independent_errors_are_returned_in_one_report_failure():
    p, c, e, reply = report_input()
    a = reply['proposal']
    a['assessment_scope']['quote'] = '不存在的范围原话'
    a['dimensions']['cash']['anchor_score'] = 0
    a['dimensions']['resources']['support'][0]['quote'] = '没有出现在输入中的人员承诺'
    a['assumptions'][0]['pass_threshold'] = ''
    a['assumptions'][0]['fail_threshold'] = ''
    with pytest.raises(ValueError) as failure:
        report_grounding.validate_report(a, p, c, e, required=True)
    text = str(failure.value)
    assert all(item in text for item in ('范围须引用用户原话', 'cash', 'resources', 'pass_threshold', 'fail_threshold'))
    assert 'resources.support[0]' in text


def test_quote_repair_names_the_exact_claim_and_missing_qualifier():
    p, c, e, reply = report_input()
    p['messages'] = [{'role': 'user', 'content': '尚未确认本项目已实现净利润。'}]
    dim = reply['proposal']['dimensions']['return']
    dim['support'][0].update(source_id='turn-0', quote='本项目已实现净利润')
    with pytest.raises(ValueError) as error:
        report_grounding.validate_report(reply['proposal'], p, c, e, required=True)
    assert 'return.support[0]' in str(error.value)
    assert '前面还有限定「尚未确认」' in str(error.value)


def test_unsupported_coverage_change_names_the_field_and_original_source():
    from tests.test_hidden_review import accepted
    p, c, e, _ = case()
    quote = '先拿10份资料对比表格与现成工具，若它们已满足要求，就不自建'
    p.update(description=quote, lifecycle={'coverage': {'opportunity': {'items': {
        'comparison': {'status': 'known', 'source': 'user', 'verified': True, 'quote': quote}}}}})
    context = advisory.packet('collection', p, c, e, None)
    value = {**accepted(), 'coverage_statuses': {'opportunity': {'comparison': 'unknown'}}}
    with pytest.raises(ValueError) as error:
        advisory.validate(value, context)
    assert 'coverage_statuses.opportunity.comparison' in str(error.value)
    assert quote in str(error.value) and '移除此项状态修订' in str(error.value)
    assert p['lifecycle']['coverage']['opportunity']['items']['comparison']['status'] == 'known'


def test_conversation_refs_do_not_count_as_evidence_and_invented_refs_still_fail():
    p, c, e, reply = report_input()
    a = reply['proposal']
    a['dimensions']['cash']['evidence_ids'] = ['turn-0', 'description', 'company', e[0]['id'], 'invented']
    a['assumptions'][0]['evidence_ids'] = ['turn-0']
    sources = {'turn-0': '用户说尚未测试', 'description': '项目描述', 'company': '公司资料'}
    support = deepcopy(a['dimensions']['cash']['support'])
    report_grounding.normalize_evidence_refs(a, e, sources)
    assert a['dimensions']['cash']['evidence_ids'] == [e[0]['id'], 'invented']
    assert a['assumptions'][0]['evidence_ids'] == []
    assert a['dimensions']['cash']['support'] == support
    with pytest.raises(ValueError, match='不存在的证据'):
        report_grounding.validate_shape(a, e)


def test_report_schema_distinguishes_user_sources_from_uploaded_evidence(monkeypatch):
    seen = {}
    def capture(client, url, payload, headers, remaining):
        seen['prompt'] = payload['messages'][0]['content']
        raise RuntimeError('captured')
    monkeypatch.setattr(llm, 'completion', capture)
    with pytest.raises(RuntimeError, match='captured'):
        llm._analyze({'base_url': 'https://model.example', 'model': 'test'}, '', {'_report_requested': True}, {}, [], [])
    assert '"maxItems":0' in seen['prompt']
    assert '"$ref":"#/$defs/SourceClaim"' in seen['prompt']
    # The storage schema still accepts old reports, but new generation requests one risk.
    schema = next(json.loads(line) for line in seen['prompt'].splitlines() if line.startswith('{"$defs":'))
    risk = schema['properties']['proposal']['properties']['strongest_objections']
    assert risk['minItems'] == risk['maxItems'] == 1


def test_one_primary_correction_receives_all_errors_and_preserves_good_fields(monkeypatch):
    for name in ('SABC_MIXTOKEN_API_KEY', 'SABC_FAL_API_KEY', 'SABC_DEEPSEEK_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    p, c, e, good = report_input()
    bad = deepcopy(good)
    bad['proposal']['dimensions']['cash']['anchor_score'] = 0
    bad['proposal']['assumptions'][0]['pass_threshold'] = ''
    calls = []
    def complete(client, url, payload, headers, remaining):
        calls.append(deepcopy(payload))
        return json.dumps(bad if len(calls) == 1 else good)
    monkeypatch.setattr(llm, 'completion', complete)
    budget = ReportCorrections()
    actual = llm.analyze({'base_url': 'https://model.example', 'model': 'test', 'report_corrections': budget},
                         '', p, c, e, [])
    assert len(calls) == 2 and budget.count == 1
    correction = calls[1]['messages'][-1]['content']
    assert all(text in correction for text in ('cash', 'pass_threshold', '一次处理', '其余正确内容保持原样'))
    assert actual['proposal']['dimensions']['strategy']['reason'] == good['proposal']['dimensions']['strategy']['reason']


def test_workload_calculation_and_scope_are_shared_by_draft_review_and_report():
    from sabc.app import build_assessment
    p, c, e, _ = case(2, 4, 'internal')
    p.update(id='workload-test', description=REPORT_DESCRIPTION, _report_requested=True,
             messages=[{'role': 'user', 'content': WORKLOAD}, {'role': 'user', 'content': SCOPE}])
    inputs = report_inputs.basis(p)
    assert inputs['workload']['minutes_per_item'] == 20
    assert inputs['scope_quotes'][-1] == {'source_id': 'turn-1', 'quote': SCOPE}
    proposal = grounded_proposal()
    proposal['decision_facts']['success_metric']['text'] += '。'
    report = build_assessment(p, c, e, proposal)
    draft_basis = model_context(p, c, e, p['messages'])['report_basis']
    review_basis = advisory.packet('report', p, c, e, report)['report_basis']
    assert draft_basis == review_basis == inputs
    note = report['snapshot']['proposal']['decision_brief']['goal_and_success']
    assert all(word in note for word in ('20.00分钟', '未独立核验', '不同样本量'))
    assert '。。' not in note
    replay = build_assessment(p, c, e, report['snapshot']['proposal'])
    assert replay['snapshot']['proposal']['decision_brief']['goal_and_success'] == note


@pytest.mark.parametrize('text', [
    '每月120份资料，目标是40小时。',
    '每月120份资料，工时未知。',
    '每月120份资料，每周共40小时。',
    '每月120份资料，20份样本共40小时。',
    '每月120份资料，合计30至40小时。',
    '每月120份资料，至少需要40小时。',
    '每月0份资料，合计40小时。',
    '每月120份资料。另一个项目合计40小时。',
])
def test_ambiguous_or_incompatible_workloads_are_not_calculated(text):
    assert report_inputs.basis({'description': text})['workload'] is None


def test_conflicting_and_retracted_numbers_do_not_silently_become_new_facts():
    p = {'description': WORKLOAD, 'messages': [{'role': 'user', 'content': '每月120份资料，合计60小时。'}]}
    assert report_inputs.basis(p)['workload'] is None
    p['messages'][0]['content'] = '更正工时：每月120份资料，合计60小时。'
    assert report_inputs.basis(p)['workload']['minutes_per_item'] == 30
    p['messages'].append({'role': 'user', 'content': '更正工时，之前40和60小时都不准确，需要重新计时。'})
    assert report_inputs.basis(p)['workload'] is None
