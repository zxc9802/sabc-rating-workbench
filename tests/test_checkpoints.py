from sabc.checkpoints import CHECKS, normalize
from sabc.lifecycle import collection_ready


def result():
    return {'reply': '信息已整理完成，现在生成报告吗？', 'questions': [],
            'dimension_coverage': {d: {'status': 'future', 'reason': '待验证'} for d in CHECKS}}


def test_one_sentence_cannot_close_six_dimensions():
    r = normalize(result(), {'description': '我想做东南亚项目'}, {}, [], [])
    assert all(d['status'] == 'ask' for d in r['dimension_coverage'].values())
    assert r['questions'] and not collection_ready({'confirmed': True, 'coverage': r['dimension_coverage']})
    assert '生成报告' not in r['reply']


def test_unknown_quote_does_not_close_cash_dimension():
    r = result()
    r['dimension_coverage']['cash']['items'] = {
        'initial': {'status': 'unknown', 'source': 'user', 'quote': '备案费用不知道'}}
    normalize(r, {}, {}, [], [{'role': 'user', 'content': '卖防晒到泰国，备案费用不知道'}])
    cash = r['dimension_coverage']['cash']
    assert cash['items']['initial']['verified']
    assert cash['items']['max_loss']['status'] == 'ask' and cash['status'] == 'ask'


def test_invented_quote_or_unknown_from_silence_is_rejected():
    for quote in ('预算10000元', '我想做东南亚项目'):
        r = result()
        r['dimension_coverage']['cash']['items'] = {
            'max_loss': {'status': 'unknown', 'source': 'user', 'quote': quote, 'verified': True}}
        normalize(r, {'description': '我想做东南亚项目'}, {}, [], [])
        assert not r['dimension_coverage']['cash']['items']['max_loss']['verified']


def test_complete_grounded_items_allow_ready_without_extra_model_call():
    r = result()
    messages = []
    for d, checks in CHECKS.items():
        r['dimension_coverage'][d]['items'] = {}
        for key, question in checks.items():
            quote = question + '：用户明确不知道该项，无法提供。'
            messages.append({'role': 'user', 'content': quote})
            r['dimension_coverage'][d]['items'][key] = {'status': 'unknown', 'source': 'user', 'quote': quote}
    normalize(r, {}, {}, [], messages)
    assert not r['questions']
    assert collection_ready({'confirmed': True, 'coverage': r['dimension_coverage']})
    r['dimension_coverage']['cash']['items']['max_loss']['verified'] = False
    assert not collection_ready({'confirmed': True, 'coverage': r['dimension_coverage']})


def test_old_dimension_labels_are_not_completion():
    assert not collection_ready({'confirmed': True, 'coverage': result()['dimension_coverage']})


def test_thai_budget_estimate_and_clearance_are_not_limits_or_roi_formula():
    r = result()
    r['dimension_coverage']['cash']['items'] = {
        'investment_limit': {'status': 'known', 'source': 'user', 'quote': '初始测款预算2万元，是拍的'},
        'max_loss': {'status': 'known', 'source': 'user', 'quote': '30天未清完库存计损失'}}
    r['dimension_coverage']['return']['items'] = {
        'metric_formula': {'status': 'known', 'source': 'user', 'quote': '整体ROI目标2.5，含投流佣金物流'}}
    normalize(r, {}, {}, [], [{'role': 'user', 'content': '初始测款预算2万元，是拍的。30天未清完库存计损失。整体ROI目标2.5，含投流佣金物流。'}])
    assert not r['dimension_coverage']['cash']['items']['investment_limit']['verified']
    assert not r['dimension_coverage']['cash']['items']['max_loss']['verified']
    assert not r['dimension_coverage']['return']['items']['metric_formula']['verified']
    assert r['questions']


def test_explicit_short_unknown_after_question_is_not_reasked():
    r = result()
    r['dimension_coverage']['cash']['items'] = {'max_loss': {'status': 'unknown', 'source': 'user', 'quote': '不知道'}}
    normalize(r, {}, {}, [], [{'role': 'assistant', 'content': '你最多能承受多少损失？'}, {'role': 'user', 'content': '不知道'}])
    assert r['dimension_coverage']['cash']['items']['max_loss']['verified']
    assert not r['dimension_coverage']['cash']['items']['investment_limit']['verified']


def test_saved_project_facts_can_be_used_without_reasking():
    r = result()
    r['dimension_coverage']['market']['items'] = {'user': {'status': 'known', 'source': 'project', 'quote': '泰国通勤女性'}}
    normalize(r, {'target_user': '泰国通勤女性'}, {}, [], [])
    assert r['dimension_coverage']['market']['items']['user']['verified']


def test_explicit_unverified_compliance_is_an_acknowledged_gap():
    for quote, expected in [('FDA通报和准入资格都未书面核验', True), ('产品配方未经独立核验', True), ('未发现违规产品', False)]:
        r = result()
        r['dimension_coverage']['risk']['items'] = {
            'compliance': {'status': 'external', 'source': 'user', 'quote': quote}}
        normalize(r, {}, {}, [], [{'role': 'user', 'content': quote}])
        assert r['dimension_coverage']['risk']['items']['compliance']['verified'] is expected


def test_corrected_roas_formula_survives_earlier_roi_wording():
    for quote, expected in [('广告ROAS等于扣退款后的实收销售额除以广告投放费', True), ('广告ROAS目标2.5', False)]:
        r = result()
        r['dimension_coverage']['return']['items'] = {
            'metric_formula': {'status': 'known', 'source': 'user', 'quote': quote}}
        normalize(r, {}, {}, [], [{'role': 'user', 'content': '之前叫整体ROI不准确。' + quote}])
        assert r['dimension_coverage']['return']['items']['metric_formula']['verified'] is expected


def test_all_grounded_checkpoints_close_without_more_model_questions_or_retrieval():
    r = result()
    r.update(reply='再细化样品和招募费用？', questions=['还需几个样品？'],
             data_requests=[{'query': '重复查询费用'}], reply_evidence_ids=['e1'])
    messages = []
    for d, checks in CHECKS.items():
        r['dimension_coverage'][d]['items'] = {}
        for key, question in checks.items():
            quote = question + '：这项我目前不知道。'
            messages.append({'role': 'user', 'content': quote})
            r['dimension_coverage'][d]['items'][key] = {'status': 'unknown', 'source': 'user', 'quote': quote}
    normalize(r, {}, {}, [], messages)
    assert collection_ready({'confirmed': True, 'coverage': r['dimension_coverage']})
    assert r['questions'] == r['data_requests'] == r['reply_evidence_ids'] == []
    assert r['reply'] == '信息已整理完成，现在生成报告吗？'


def test_supplement_preserves_grounded_unknown_without_reasking():
    quote = '售价与单件成本完全未知'
    prior = {'status': 'unknown', 'source': 'user', 'quote': quote, 'verified': True}
    project = {'messages': [{'role': 'user', 'content': quote}],
               'lifecycle': {'coverage': {'return': {'items': {'costs': prior}}}}}
    r = normalize(result(), project, {}, [], [{'role': 'user', 'content': '首笔3000元包含在测款预算里'}])
    assert r['dimension_coverage']['return']['items']['costs'] == prior


def test_new_quoted_change_can_update_or_reopen_prior_cash_limit():
    prior = {'status': 'known', 'source': 'user', 'quote': '总投入上限3万元', 'verified': True}
    project = {'messages': [{'role': 'user', 'content': prior['quote']}],
               'lifecycle': {'coverage': {'cash': {'items': {'investment_limit': prior}}}}}
    for quote, status in [('总投入上限改为2万元', 'known'), ('总投入上限需要重新讨论', 'ask')]:
        r = result()
        r['dimension_coverage']['cash']['items'] = {
            'investment_limit': {'status': status, 'source': 'user', 'quote': quote}}
        normalize(r, project, {}, [], [{'role': 'user', 'content': quote}])
        item = r['dimension_coverage']['cash']['items']['investment_limit']
        assert item['status'] == status
        assert item['verified'] is (status == 'known')
        if status == 'known': assert item['quote'] == quote
def test_explicit_unknown_costs_and_unavailable_outsourcing_do_not_loop():
    r = normalize(result(), {}, {}, [], [{'role': 'user', 'content':
        '持续成本的广告、佣金、物流和客服金额都未知。外包人员和代理均未落实，报价仍未知。'}])
    assert r['dimension_coverage']['return']['items']['costs']['status'] == 'unknown'
    assert r['dimension_coverage']['resources']['items']['dependencies']['status'] == 'unknown'
    for dim, key in [('return', 'metric_formula'), ('resources', 'owner'), ('cash', 'investment_limit')]:
        assert not r['dimension_coverage'][dim]['items'][key]['verified']


def test_internal_time_formula_does_not_require_monetary_roi():
    for quote, expected in [('旧流程全部工时减去新流程全部人员总工时', True),
                            ('ROI目标2.5，预计节省3小时', False)]:
        r = result()
        r['dimension_coverage']['return']['items'] = {
            'metric_formula': {'status': 'known', 'source': 'user', 'quote': quote}}
        normalize(r, {}, {}, [], [{'role': 'user', 'content': quote + '。现金收益未知，不能算ROI。'}])
        assert r['dimension_coverage']['return']['items']['metric_formula']['verified'] is expected


def test_asking_again_with_old_quote_cannot_erase_resolved_failure_condition():
    prior = {'status': 'known', 'source': 'user', 'quote': '重大金额错漏立即停用并回人工', 'verified': True}
    project = {'messages': [{'role': 'user', 'content': prior['quote']}],
               'lifecycle': {'coverage': {'risk': {'items': {'failure': prior}}}}}
    r = result()
    r['dimension_coverage']['risk']['items'] = {
        'failure': {'status': 'ask', 'source': 'user', 'quote': prior['quote']}}
    normalize(r, project, {}, [], [{'role': 'user', 'content': '补充工时公式，不改停止条件'}])
    assert r['dimension_coverage']['risk']['items']['failure'] == prior


def test_unknown_declaration_fallback_does_not_treat_questions_or_old_facts_as_answers():
    from sabc.checkpoints import explicit_unavailable
    for message in ['外包均未落实吗？', '外包此前均未落实，现在已落实', '外包并非均未落实',
                    '外包费用未知，但人员已确认', '需要核查外包是否均未落实?']:
        assert explicit_unavailable('dependencies', message) == ''
    assert explicit_unavailable('costs', '持续成本未知吗？') == ''
