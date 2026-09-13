import pytest

from sabc.checkpoints import normalize


def check(dimension, key, quote, status='known', returned=True):
    items = {key: {'status': status, 'source': 'user', 'quote': quote}} if returned else {}
    result = {'questions': [], 'dimension_coverage': {dimension: {'items': items}}}
    normalize(result, {}, {}, [], [{'role': 'user', 'content': quote}])
    return result['dimension_coverage'][dimension]['items'][key]


@pytest.mark.parametrize('quote', ['做过本项目测试。', '我们进行过这个项目的试点。'])
def test_explicit_test_history_word_order_is_recognized(quote):
    item = check('return', 'validation_history', quote)
    assert item['verified'] and item['quote'] == quote


@pytest.mark.parametrize('quote', ['计划做过本项目测试以后再决定。', '希望进行过这个项目的试点再评价。'])
def test_future_intentions_are_not_test_history(quote):
    assert not check('return', 'validation_history', quote)['verified']


def test_total_cash_occupancy_is_an_explicit_investment_limit():
    quote = '总项目现金占用上限5000元（包括此前已支付的1000元）'
    assert check('cash', 'investment_limit', quote)['verified']
    assert not check('cash', 'investment_limit', '首期现金占用上限2000元')['verified']


def test_dated_trial_with_observed_sample_is_history_but_future_date_is_not():
    assert check('return', 'validation_history', '试点是2026年8月3日至8月30日，共4周1600条。')['verified']
    assert not check('return', 'validation_history', '试点是2999年8月3日至8月30日，共4周1600条。')['verified']


def test_explicit_unknown_migration_cost_is_not_reopened_when_model_omits_it():
    quote = '其他店铺的迁移额外工时、费用、效果已经明确未知'
    item = check('replication', 'extra', quote, returned=False)
    assert item['verified'] and item['status'] == 'unknown'
    for text in ('迁移费用未知吗？', '迁移费用不再未知，报价已经确认500元', '过去迁移成本未知，现在报价500元'):
        assert not check('replication', 'extra', text, returned=False)['verified']


def test_unknown_paraphrase_uses_explicit_user_quote_instead_of_reopening():
    quote = '没有下一家店的扩展计划，其他店铺迁移额外工时和费用明确未知'
    result = {'questions': [], 'dimension_coverage': {'replication': {'items': {
        'extra': {'status': 'unknown', 'source': 'user', 'quote': '迁移成本未知。'}}}}}
    normalize(result, {}, {}, [], [{'role': 'user', 'content': quote}])
    item = result['dimension_coverage']['replication']['items']['extra']
    assert item['verified'] and item['status'] == 'unknown' and item['quote'] == quote


def test_grounded_internal_users_are_saved_when_model_omits_project_field():
    quote = '三家既有店的两名运营负责订单对账'
    result = {'questions': [], 'dimension_coverage': {'market': {'items': {
        'user': {'status': 'known', 'source': 'user', 'quote': quote}}}}}
    normalize(result, {}, {}, [], [{'role': 'user', 'content': quote}])
    assert result['project_patch']['target_user'] == quote


@pytest.mark.parametrize('existing', [None, '已确认的内部使用者'])
def test_user_field_fallback_does_not_invent_or_overwrite(existing):
    result = {'questions': [], 'dimension_coverage': {'market': {'items': {
        'user': {'status': 'known', 'source': 'user', 'quote': '未曾提供的目标客户'}}}}}
    normalize(result, {'target_user': existing}, {}, [], [{'role': 'user', 'content': '我想改善流程'}])
    assert 'target_user' not in result.get('project_patch', {})
