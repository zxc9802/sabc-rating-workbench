from copy import deepcopy
import pytest
from sabc.standard import validate_rubric_reasons


@pytest.mark.parametrize('key,reason', [
    ('opportunity', '现有可行备选中最优，但未穷尽所有备选，故未给5。'),
    ('risk', '已有明确控制，但风险并非低到无需管理，故给4。'),
    ('market', '内部价值明确，但非外部大市场增长逻辑，故给4。'),
])
def test_prohibited_extra_requirement_is_rejected_without_changing_score(key, reason):
    proposal = {'dimensions': {key: {'score': 4, 'reason': reason}}}
    before = deepcopy(proposal)
    with pytest.raises(ValueError, match='额外门槛'):
        validate_rubric_reasons(proposal, {'project_type': 'internal'})
    assert proposal == before


@pytest.mark.parametrize('key,reason', [
    ('opportunity', '已比较的PowerQuery现金成本更低，但本案减少人工更多，取舍尚不唯一。'),
    ('risk', '格式变更经常超出维护排期，现有控制依然需要负责人介入。'),
    ('market', '内部任务每月仅一次且未影响主业，价值相对有限。'),
])
def test_scope_relevant_limitations_remain_valid(key, reason):
    proposal = {'dimensions': {key: {'score': 3, 'reason': reason}}}
    before = deepcopy(proposal)
    validate_rubric_reasons(proposal, {'project_type': 'internal'})
    assert proposal == before
