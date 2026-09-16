from sabc.standard import ground_low_scores
import pytest


@pytest.mark.parametrize('objections', [
    ['实际效果尚未验证，可能增加复核工时。'],
    ['需核查需求变化影响', '需核查成本变化影响', '需核查资源变化影响'],
])
def test_report_accepts_one_main_risk_and_legacy_three_without_changing_scores(objections):
    from copy import deepcopy
    from sabc import report_grounding
    from tests.test_report_timeouts import report_input
    p, c, e, reply = report_input()
    proposal = reply['proposal']
    before = deepcopy(proposal['dimensions'])
    proposal['strongest_objections'] = objections
    report_grounding.validate_report(proposal, p, c, e, required=True)
    assert proposal['dimensions'] == before


@pytest.mark.parametrize('objections', [[], ['  '], ['第一项', '', '第三项'], ['问题'] * 4])
def test_main_risk_still_requires_meaningful_content(objections):
    from sabc import report_grounding
    from tests.test_report_timeouts import report_input
    p, c, e, reply = report_input()
    reply['proposal']['strongest_objections'] = objections
    with pytest.raises(ValueError, match='最大隐患'):
        report_grounding.validate_report(reply['proposal'], p, c, e, required=True)


def test_possible_better_alternative_does_not_become_confirmed_low_score():
    quote = '把这每周6小时用于现有SOP优化可能更划算'
    proposal = {'dimensions': {'opportunity': {
        'score': 2.5, 'basis': 'fact', 'reason': quote, 'negative_fact': quote}}}
    ground_low_scores(proposal, {}, {}, [], [{'role': 'user', 'content': quote}])
    assert proposal['dimensions']['opportunity']['score'] is None
    assert proposal['dimensions']['opportunity']['basis'] == 'unknown'


def test_explicit_negative_plan_arithmetic_can_support_low_score():
    quote = '按售价69元和全部单件成本97元，每卖一单亏28元，原方案不改'
    proposal = {'dimensions': {'return': {
        'score': 1, 'basis': 'fact', 'reason': quote, 'negative_fact': quote}}}
    ground_low_scores(proposal, {}, {}, [], [{'role': 'user', 'content': quote}])
    assert proposal['dimensions']['return']['score'] == 1


def test_model_invented_negative_or_missing_quote_is_deferred_without_raising_score():
    for quote in [None, '', '每月亏损5000元且无法调整']:
        proposal = {'dimensions': {'return': {
            'score': 1, 'basis': 'fact', 'reason': '负面', 'negative_fact': quote}}}
        ground_low_scores(proposal, {}, {}, [], [{'role': 'user', 'content': '还没测过真实利润'}])
        assert proposal['dimensions']['return']['score'] is None


def test_model_diagnostics_locate_nested_field_without_logging_value():
    import json
    from pydantic import ValidationError
    from sabc.schema import Proposal
    from sabc.model_output import format_failure
    try:
        Proposal.model_validate({'dimensions': {'cash': {'negative_fact': {'private': 'do-not-log'}}}})
    except ValidationError as error:
        details = format_failure(error, '').details
    assert details['error_fields'] == ['dimensions.cash.negative_fact']
    assert 'do-not-log' not in json.dumps(details)
