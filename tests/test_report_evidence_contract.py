"""Original September 14 reports plus counterexamples at the production boundaries."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from sabc import advisory, checkpoints, rating, dimension_sources
from sabc.fact_boundaries import qualification
from sabc import report_grounding
from tests.report_fixtures import grounded_proposal, REPORT_DESCRIPTION


def archived(name):
    return json.loads((Path(__file__).parent / 'fixtures' / f'{name}-review.json').read_text())


@pytest.mark.parametrize('name', ['tripadvisor', 'duolingo'])
def test_original_contradictory_report_cannot_pass_review(name):
    s = archived(name)
    candidate = {'result': s['result'], 'snapshot': s}
    context = advisory.packet('report', s['project'], s['company'], s['evidence'], candidate)
    with pytest.raises(ValueError):
        advisory.validate({'checks': {k: 'pass' for k in advisory.PERSPECTIVES}}, context)


@pytest.mark.parametrize('name', ['tripadvisor', 'duolingo'])
def test_nr_keeps_eight_rows_and_computes_evidence(name):
    s = archived(name)
    with patch.object(rating, 'evidence_strength', wraps=rating.evidence_strength) as strength:
        result = rating.assess(s['project'], s['company'], s['evidence'], s['proposal'])
    assert result['grade'] == 'NR' and result['base_score'] is None
    assert len(result['dimensions']) == 8
    assert strength.call_count > 0 and result['unique_sources'] == 1
    assert result['evidence_level'] == 'E0'  # Unverified attachments must stay unverified.
    for item in result['dimensions']:
        if item['score'] is None:
            assert item['weighted'] is None and item['reason']


def test_long_unavailable_budget_answer_is_resolved():
    p = archived('tripadvisor')['project']
    answer = next(m['content'] for m in p['messages']
                  if m['role'] == 'user' and '历史总投入、未来投入上限' in m['content'])
    assert checkpoints.explicit_unavailable('investment_limit', answer)


@pytest.mark.parametrize('text', [
    '没有获得获批的后续投入项目清单，不能确认投入比例',
    '并没有本轮证据证明已违规、牌照无法获得或必然停止经营',
    '尚未拿到订阅分部现金流报表',
])
def test_no_proof_is_not_a_negative_business_fact(text):
    assert qualification(text, 'unknown')['knowledge'] in ('unknown', 'not_obtained')


def test_completion_and_question_count_are_not_left_in_question_reply():
    reply = checkpoints.question_reply('第一阶段问答已完成，正在整理报告。剩下两个问题：', [], ['总投入未知吗？'])
    assert '已完成' not in reply and '两个' not in reply
    assert '总投入未知吗？' in reply


def test_global_scope_does_not_require_country_for_public_research():
    p = archived('duolingo')['project']
    answer = next(m['content'] for m in p['messages'] if m['role'] == 'user' and m['content'].startswith('全球，'))
    result = dimension_sources.rule_plan(p, answer, [])
    assert not any('一个目标国家地区' in v['reason'] for v in result['missing_parameters'])


def supported_case():
    quote = '本业务现金占用100万元，可用现金200万元，安全线50万元，回款30天。'
    p = {'description': REPORT_DESCRIPTION, 'messages': [{'role':'user','content':quote}]}
    a = grounded_proposal(quote=quote, source_id='turn-0')
    for key, d in a['dimensions'].items():
        if key != 'cash': d.update(score=None, anchor_score=None, support=[])
    return p, a


def test_positive_score_survives_when_same_business_support_is_present():
    p,a=supported_case()
    a['dimensions']['cash'].update(score=4,anchor_score=4)
    before=deepcopy(a)
    report_grounding.validate(a,p,{},[],required=True)
    assert a==before


def test_pdf_wrapping_is_allowed_without_changing_words_or_numbers():
    text='Experiences $ 278.6\n$ 270.5 3 %'
    assert report_grounding.match_quote({'source_id':'evidence-e1','quote':'Experiences $ 278.6 $ 270.5 3 %'}, {'evidence-e1':text})
    assert not report_grounding.match_quote({'source_id':'evidence-e1','quote':'Experiences $ 300.0 $ 270.5 3 %'}, {'evidence-e1':text})


def test_explicit_group_allocation_is_distinct_from_group_cash_balance():
    p,a=supported_case()
    quote='集团已批准本业务现金额度100万元，本业务占用60万元，安全线20万元，回款30天。'
    p['messages'][0]['content']=quote
    a['dimensions']['cash']['support'][0]['quote']=quote
    report_grounding.validate(a,p,{},[],required=True)


def test_group_cash_alone_cannot_prove_segment_resources():
    p,a=supported_case()
    quote='集团现金200万元。'
    p['messages'][0]['content']=quote
    a['dimensions']['resources']=deepcopy(a['dimensions']['cash'])
    a['dimensions']['cash'].update(score=None,anchor_score=None,support=[])
    a['dimensions']['resources']['support'][0]['quote']=quote
    with pytest.raises(ValueError,match='集团财务口径'):
        report_grounding.validate(a,p,{},[],required=True)


@pytest.mark.parametrize('change', ['missing', 'background', 'wrong_source', 'unknown', 'group', 'wrong_anchor'])
def test_positive_score_requires_usable_original_support(change):
    p,a=supported_case();d=a['dimensions']['cash'];support=d['support'][0]
    if change=='missing': d['support']=[]
    elif change=='background': support['use']='background'
    elif change=='wrong_source': support['source_id']='turn-1'
    elif change=='unknown':
        support['quote']='本业务独立现金流尚未取得';p['messages'][0]['content']=support['quote']
    elif change=='group':
        support['quote']='集团现金及现金等价物843.2百万美元';p['messages'][0]['content']=support['quote']
    else:d['anchor_score']=3
    with pytest.raises(ValueError): report_grounding.validate(a,p,{},[],required=True)


def test_inferred_zero_cost_does_not_follow_from_reusable_content():
    p,a=supported_case()
    a['pros']=['课程可以复用，边际零成本']
    with pytest.raises(ValueError,match='确定性结论'):
        report_grounding.validate(a,p,{},[],required=True)


def test_suggestion_and_historical_period_never_become_confirmed_targets():
    p,a=supported_case()
    p['timeframe']='2026年第二季度（业绩报告期间，同比对比2025年第二季度）'
    a['decision_facts']['success_metric']={'kind':'suggestion','text':'付费账户增长10%','source_id':'','quote':''}
    a['decision_brief']={'goal_and_success':'成功标准为双位数增长','maximum_loss':'仅研究工时','upgrade_s':'机会成本五维4分且AI跨国盈利'}
    report_grounding.validate(a,p,{},[],required=True)
    report_grounding.apply_decision_facts(p,a)
    assert p['timeframe'] is None and '2026' in p['data_period']
    assert p['success_metric'] is None
    assert '建议、待确认' in a['decision_brief']['goal_and_success']
    assert a['decision_brief']['maximum_loss'].startswith('未知')
    assert a['decision_brief']['upgrade_s']==rating.upgrade_requirements()['upgrade_s']
    assert not report_grounding.historical_period('计划在业绩报告发布后30天复评')


def test_reported_threshold_cannot_be_a_rewritten_or_clipped_claim():
    p,a=supported_case()
    p['messages'].append({'role':'user','content':'不能认定已满足双位数增长；未来标准未知。'})
    a['decision_facts']['success_metric']={'kind':'reported','text':'已满足双位数增长','source_id':'turn-1','quote':'已满足双位数增长'}
    with pytest.raises(ValueError):report_grounding.validate(a,p,{},[],required=True)


@pytest.mark.parametrize('prefix',['没有证据证明','尚未确认','不能认定','并未获得'])
def test_source_quotes_cannot_drop_leading_negation(prefix):
    quote='本业务拥有可用资金'
    assert not report_grounding.match_quote({'source_id':'turn-0','quote':quote},{'turn-0':prefix+quote})
    assert report_grounding.match_quote({'source_id':'turn-0','quote':quote},{'turn-0':'过去没有确认；现在已确认'+quote})


def test_s_rule_five_dimensions_match_engine():
    rule=rating.upgrade_requirements()['upgrade_s']
    names={'strategy':'公司方向','market':'需求','return':'回报','resources':'人手与能力','replication':'复用成果'}
    assert all(names[k] in rule for k in rating.S_DIMENSIONS)
    assert '90' in rule and 'E3' in rule and '必须停止或限制评级' in rule


def test_original_operating_statement_closes_history_without_reasking():
    assert checkpoints.validation_answer('validation_history','已经商业化运营的付费订阅业务','known','user',[])


def test_actual_absence_and_future_unknown_remain_distinct():
    assert qualification('已经核实不存在合法授权','known')['knowledge']=='reported_absent'
    assert not checkpoints.explicit_unavailable('investment_limit','不是未知，总投入上限确认100万元。')


def test_jurisdiction_is_still_needed_for_regulatory_conclusion():
    result=dimension_sources.rule_plan({'description':'产品：软件；全球隐私合规法规'},'全球隐私法规',[])
    assert any('司法辖区' in item['reason'] for item in result['missing_parameters'])


def test_research_uses_only_explicitly_matched_company_baseline():
    from tests.test_rating import case
    p,c,e,_=case()
    p.update(description=REPORT_DESCRIPTION, framing={'purpose':'research'})
    a=grounded_proposal()
    assert any('被研究业务' in item for item in rating.missing_fields(p,c,a['assessment_scope']))
    a['assessment_scope']['company_baseline']=True
    with pytest.raises(ValueError,match='账号公司基线'):
        report_grounding.validate(a,p,c,e,required=True)
    quote='确认公司基线的现金、预算、团队与战略均属于本次被评估业务的运营方，适用于本次评估。'
    p['messages']=[{'role':'user','content':quote}]
    a['assessment_scope'].update(baseline_source_id='turn-0',baseline_quote=quote)
    report_grounding.validate(a,p,c,e,required=True)
    assert rating.missing_fields(p,c,a['assessment_scope'])==[]


def test_confirmed_decision_facts_preserve_eligible_positive_rating():
    from tests.test_rating import case
    p,c,e,proposal=case(level=2,score=4)
    p.update(description=REPORT_DESCRIPTION, messages=[{'role':'user','content':'经营目标是降低成本；成功标准是贡献毛利为正；未来验证周期为90天。'}])
    a=grounded_proposal(proposal)
    for field in ('business_goal','success_metric','timeframe'):
        a['decision_facts'][field]={'kind':'reported','text':p[field], 'source_id':'turn-0','quote':p['messages'][0]['content']}
    report_grounding.validate(a,p,c,e,required=True)
    report_grounding.apply_decision_facts(p,a)
    result=rating.assess(p,c,e,a)
    assert result['grade']=='A' and result['base_score']==80
    assert p['timeframe']=='90天' and p['success_metric']=='贡献毛利为正'
