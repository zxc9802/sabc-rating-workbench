import pytest
from sabc.llm import guide
from sabc.templates import TEMPLATES


@pytest.mark.parametrize('kind',list(TEMPLATES))
def test_project_type_changes_value_question(kind):
    result=guide({'project_type':kind,'target_user':'已知使用者','business_goal':'已知目标'},'继续')
    assert result['field']=='value_mechanism'
    assert result['reply']==TEMPLATES[kind]['value_mechanism']
