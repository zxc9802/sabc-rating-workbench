from sabc.standard import ground_low_scores


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
