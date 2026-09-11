from tests.test_rating import case
from sabc import lifecycle


def draft_reply():
    proposal = case()[3]
    for item in proposal['assumptions']:
        item.update(validation_method='核对原始记录', pass_threshold='收入覆盖全部成本', fail_threshold='达到损失上限停止')
    return {'mode': 'model', 'reply': '正在整理判断', 'project_patch': {}, 'questions': [],
            'proposal': proposal, 'dimension_coverage': {
                key: {'status': 'known', 'reason': '已提供具体判断依据'} for key in lifecycle.DIMENSIONS},
            'stage_review': {'conclusion': 'trial', 'summary': '值得小额验证', 'next_action': '核对完整成本', 'next_review_days': 14}}

