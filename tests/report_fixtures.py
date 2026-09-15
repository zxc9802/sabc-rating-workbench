from tests.test_rating import case
from sabc import lifecycle

REPORT_DESCRIPTION = '评估本公司已有订单交付业务，以下为合成测试资料。'


def grounded_proposal(proposal=None, quote='测试用记录，非真实业务结果', source_id='evidence-e1'):
    """Valid source-link contract for parser tests; not a business benchmark."""
    from copy import deepcopy
    proposal = deepcopy(proposal if proposal is not None else case()[3])
    proposal.update(grounding_version=1,
        assessment_scope={'subject':'订单交付业务','level':'project','source_id':'description','quote':REPORT_DESCRIPTION},
        decision_facts={key:{'text':'','kind':'unknown','source_id':'','quote':''}
                        for key in ('business_goal','success_metric','timeframe','maximum_loss')},
        strongest_objections=['需核查需求变化影响','需核查成本变化影响','需核查资源变化影响'])
    for dim in proposal['dimensions'].values():
        if dim.get('score') is not None:
            dim.update(anchor_score=int(dim['score']),support=[{'source_id':source_id,'quote':quote,
                'subject':'订单交付业务','scope':'project','metric':'合成案例判断依据','period':'未注明','unit':'不适用','use':'support'}])
    return proposal


def checkpoint_items(dimension, status='known'):
    from sabc.checkpoints import CHECKS
    return {key: {'status': status, 'quote': '测试中已提供的具体依据', 'source': 'user', 'verified': True}
            for key in CHECKS[dimension]}


def draft_reply():
    proposal = case()[3]
    for item in proposal['assumptions']:
        item.update(validation_method='核对原始记录', pass_threshold='收入覆盖全部成本', fail_threshold='达到损失上限停止')
    return {'mode': 'model', 'reply': '正在整理判断', 'project_patch': {}, 'questions': [],
            'proposal': proposal, 'dimension_coverage': {
                key: {'status': 'known', 'reason': '已提供具体判断依据', 'items': checkpoint_items(key)} for key in lifecycle.DIMENSIONS},
            'stage_review': {'conclusion': 'trial', 'summary': '值得小额验证', 'next_action': '核对完整成本', 'next_review_days': 14}}
