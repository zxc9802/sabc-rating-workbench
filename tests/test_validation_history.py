from copy import deepcopy

from sabc.checkpoints import CHECKS, normalize
from sabc.lifecycle import collection_ready


VALIDATION = ('validation_history', 'validation_results', 'validation_records', 'validation_transfer')


def interview(answers=None):
    result = {'reply': '信息已整理完成，现在生成报告吗？', 'questions': [], 'dimension_coverage': {}}
    messages = []
    for dimension, checks in CHECKS.items():
        items = {}
        for key, question in checks.items():
            if key in VALIDATION:
                continue
            quote = question + '这项我目前不知道。'
            messages.append({'role': 'user', 'content': quote})
            items[key] = {'status': 'unknown', 'source': 'user', 'quote': quote}
        result['dimension_coverage'][dimension] = {'status': 'known', 'reason': '验收输入', 'items': items}
    for key, (status, quote) in (answers or {}).items():
        messages.append({'role': 'user', 'content': quote})
        result['dimension_coverage']['return']['items'][key] = {'status': status, 'source': 'user', 'quote': quote}
    return result, messages


def ready(result):
    return collection_ready({'confirmed': True, 'coverage': result['dimension_coverage']})


def test_legacy_complete_interview_cannot_close_without_validation_history():
    result, messages = interview()
    normalize(result, {}, {}, [], messages)
    assert not ready(result)
    assert '测试' in result['questions'][0]


def test_planned_targets_cannot_stand_in_for_past_tests():
    quote = '计划测试20笔订单，目标每周从8小时降到5小时。'
    result, messages = interview({key: ('known', quote) for key in VALIDATION})
    normalize(result, {}, {}, [], messages)
    assert not ready(result)
    assert not result['dimension_coverage']['return']['items']['validation_history']['verified']
    assert not result['dimension_coverage']['return']['items']['validation_results']['verified']


def test_explicit_no_test_skips_nonexistent_results_but_still_asks_about_similar_cases():
    result, messages = interview({'validation_history': ('known', '本项目还没进行过测试。')})
    normalize(result, {}, {}, [], messages)
    items = result['dimension_coverage']['return']['items']
    assert items['validation_history']['verified']
    assert items['validation_results']['status'] == items['validation_records']['status'] == 'future'
    assert items['validation_results']['verified'] and items['validation_records']['verified']
    assert not items['validation_transfer']['verified'] and not ready(result)
    assert '类似' in result['questions'][0]


def test_tested_without_results_or_records_requires_followup():
    quote = '这个方案上周已经测试过。'
    result, messages = interview({key: ('known', quote) for key in VALIDATION[:3]})
    normalize(result, {}, {}, [], messages)
    items = result['dimension_coverage']['return']['items']
    assert items['validation_history']['verified']
    assert not items['validation_results']['verified'] and not items['validation_records']['verified']
    assert not ready(result)


def test_report_can_follow_explicit_results_and_missing_records_without_inventing_evidence():
    result, messages = interview({
        'validation_history': ('known', '这个方案上周已经测试过。'),
        'validation_results': ('known', '上周同一店铺100笔订单，原流程8小时，新流程合计5小时，观察到0次重大漏检；具体费用未知。'),
        'validation_records': ('unknown', '测试结果只是我的回忆，没有保存日志，也无法提供原始记录。'),
        'validation_transfer': ('unknown', '没有类似项目的成功案例。'),
    })
    evidence = []
    normalize(result, {}, {}, evidence, messages)
    assert ready(result) and not result['questions']
    assert evidence == [] and not result.get('proposal')


def test_no_test_answer_is_reused_but_new_test_reopens_missing_results():
    result, messages = interview({
        'validation_history': ('known', '本项目还没进行过测试。'),
        'validation_transfer': ('unknown', '没有类似项目的成功案例。'),
    })
    normalize(result, {}, {}, [], messages)
    assert ready(result)
    project = {'messages': messages, 'lifecycle': {'coverage': deepcopy(result['dimension_coverage'])}}
    followup = {'reply': '', 'questions': [], 'dimension_coverage': {}}
    normalize(followup, project, {}, [], [{'role': 'user', 'content': '只补充预算，其他信息不变。'}])
    assert ready(followup)
    changed, _ = interview({'validation_history': ('known', '现在这个方案已经实际测试过。')})
    normalize(changed, project, {}, [], [{'role': 'user', 'content': '现在这个方案已经实际测试过。'}])
    items = changed['dimension_coverage']['return']['items']
    assert not items['validation_results']['verified'] and not items['validation_records']['verified']
    assert not ready(changed)
    stale = deepcopy(result)
    stale['dimension_coverage']['return']['items']['validation_history'] = {
        'status': 'known', 'source': 'user', 'quote': '现在这个方案已经实际测试过。'}
    normalize(stale, project, {}, [], [{'role': 'user', 'content': '现在这个方案已经实际测试过。'}])
    assert not ready(stale)
    assert not stale['dimension_coverage']['return']['items']['validation_results']['verified']


def test_missing_logs_do_not_mean_no_tests_were_performed():
    result, messages = interview({'validation_history': ('unknown', '没有工时日志或抽样审计记录。')})
    normalize(result, {}, {}, [], messages)
    assert not result['dimension_coverage']['return']['items']['validation_history']['verified']
    assert not ready(result)


def test_short_answer_is_only_used_for_the_question_it_answers():
    result, _ = interview({'validation_history': ('known', '没做过')})
    messages = [{'role': 'assistant', 'content': '本项目做过测试吗？'}, {'role': 'user', 'content': '没做过'}]
    normalize(result, {}, {}, [], messages)
    items = result['dimension_coverage']['return']['items']
    assert items['validation_history']['verified'] and items['validation_results']['status'] == 'future'
    other, _ = interview({'validation_history': ('known', '没做过')})
    messages[0]['content'] = '做过市场调研吗？'
    normalize(other, {}, {}, [], messages)
    assert not other['dimension_coverage']['return']['items']['validation_history']['verified']


def test_unknown_future_results_or_prices_cannot_close_test_history():
    for quote in ('已经计划下周测试20筆，结果未知。', '测试费用还没有报价。'):
        result, messages = interview({key: ('unknown', quote) for key in VALIDATION})
        normalize(result, {}, {}, [], messages)
        assert not result['dimension_coverage']['return']['items']['validation_history']['verified']
        assert not ready(result)


def test_similar_success_claim_needs_details_and_transfer_conditions():
    for quote, expected in [('有类似项目的成功案例。', False),
                            ('类似案例去年处理100单，工时下降30%，相同的是Excel核对，不同的是供应商格式。', True)]:
        result, messages = interview({'validation_transfer': ('known', quote)})
        normalize(result, {}, {}, [], messages)
        assert result['dimension_coverage']['return']['items']['validation_transfer']['verified'] is expected


def test_short_explicit_unknown_is_kept_for_results_records_and_similar_cases():
    for key, question, answer in [
        ('validation_results', '测试结果和实际成本是多少？', '不知道'),
        ('validation_records', '能提供测试的原始记录吗？', '没有'),
        ('validation_transfer', '有类似项目的成功案例吗？', '没有'),
    ]:
        result, _ = interview({key: ('unknown', answer)})
        messages = [{'role': 'assistant', 'content': question}, {'role': 'user', 'content': answer}]
        normalize(result, {}, {}, [], messages)
        assert result['dimension_coverage']['return']['items'][key]['verified']
