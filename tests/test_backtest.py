from datetime import date
from tests.test_rating import case
from sabc.backtest import replay


def test_unlabelled_replay_does_not_invent_accuracy():
    p,c,e,a=case()
    r=replay([{'project':p,'company':c,'evidence':e,'proposal':a}],date(2026,9,9))
    assert r['agreement_rate'] is None and r['cases'][0]['deterministic']


def test_invalid_case_does_not_hide_other_results():
    p,c,e,a=case(1)
    r=replay([{}, {'project':p,'company':c,'evidence':e,'proposal':a,'expected_grade':'B'}],date(2026,9,9))
    assert r['errors']==1 and r['labelled_count']==1 and r['agreement_rate']==1


def test_description_paraphrase_preserves_fixed_structured_rating():
    p,c,e,a=case(1)
    first=replay([{'project':p,'company':c,'evidence':e,'proposal':a}],date(2026,9,9))
    p['description']='我们希望通过新的交付方式降低企业客户服务成本。'
    second=replay([{'project':p,'company':c,'evidence':e,'proposal':a}],date(2026,9,9))
    assert first['cases'][0]['result']==second['cases'][0]['result']
