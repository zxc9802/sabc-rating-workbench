from sabc.context import model_context


def test_history_sent_once_and_pending_facts_preserved():
    messages=[{'role':'user','content':str(i)} for i in range(40)]
    project={'id':'p','messages':messages,'proposal':{'huge':'old'},'description':'原文','risks':'已确认风险','pending_patch':{'budget_requested':100}}
    c=model_context(project,{},[],messages)
    assert 'messages' not in c['project'] and 'proposal' not in c['project']
    assert c['conversation']==messages[-16:]
    assert c['project']['risks']=='已确认风险'
    assert c['project']['pending_patch']=={'budget_requested':100}
    assert c['context_limits']['older_messages_omitted']==24


def test_evidence_limits_explicit_and_old_version_excluded():
    evidence=[{'id':str(i),'content':'x'*7000} for i in range(15)]
    evidence[0]['supersedes']='14'
    c=model_context({}, {}, evidence,[])
    assert len(c['evidence'])==12
    assert c['context_limits']['evidence_omitted']==2
    assert all(len(e['content'])==6000 and e['context_truncated'] for e in c['evidence'])
    assert '14' not in [e['id'] for e in c['evidence']]


def test_previous_questions_remain_only_in_conversation():
    question = '出现什么情况会停止？'
    messages = [{'role': 'assistant', 'content': question}, {'role': 'user', 'content': '重大漏报即停止。'}]
    project = {'interview': {'state': 'gathering', 'gaps': ['return'], 'questions': [question]}}
    c = model_context(project, {}, [], messages)
    assert str(c).count(question) == 1
    assert c['conversation'][-1] == messages[-1]
    assert c['project']['interview']['gaps'] == ['return']
    assert project['interview']['questions'] == [question]


def test_report_preserves_early_user_corrections_without_old_report_prose():
    messages = [{'role': 'user', 'content': '更正：ROAS只除广告费，净贡献还要扣代工和包材。'}]
    messages += [{'role': 'assistant', 'content': '旧口径草稿'}, {'role': 'user', 'content': '其他未知'}] * 20
    project = {'_report_requested': True, '_previous_stage_report': {
        'id': 'old', 'result': {'grade': 'B', 'dimensions': [{'key': 'return', 'score': 3, 'reason': '旧公式'}],
                             'validation_plan': [{'method': '净贡献=收入-广告费'}]}}}
    c = model_context(project, {}, [], messages)
    assert c['conversation'][0] == {**messages[0], 'source_id': 'turn-0'}
    assert all(m['role'] == 'user' for m in c['conversation'])
    assert c['project']['previous_stage_report']['id'] == 'old'
    assert not {'grade', 'base_score', 'dimensions'} & c['project']['previous_stage_report'].keys()
    assert '旧公式' not in str(c) and '净贡献=收入-广告费' not in str(c)
    assert '旧口径草稿' not in str(c)


def test_report_user_history_is_bounded_and_latest_correction_kept():
    messages = [{'role': 'user', 'content': '旧资料' * 10000}, {'role': 'user', 'content': '最新总上限3万，损失1.5万。'}]
    c = model_context({'_report_requested': True}, {}, [], messages)
    assert sum(len(m['content']) for m in c['conversation']) == 24000
    assert c['conversation'][-1] == {**messages[-1], 'source_id': 'turn-1'}
    assert c['context_limits']['conversation_chars_truncated']


def test_report_does_not_treat_model_coverage_summary_as_new_evidence():
    from copy import deepcopy
    from sabc.lifecycle import initial
    project = {'_report_requested': True, 'lifecycle': initial()}
    project['lifecycle']['coverage']['risk'] = {'reason': '旧模型推断质量条件未知', 'status': 'unknown'}
    before = deepcopy(project)
    messages = [{'role': 'user', 'content': '重大金额漏报立即停止，不追加预算。'}]
    c = model_context(project, {}, [{'id': 'proof', 'content': '已核验记录'}], messages)
    assert 'lifecycle' not in c['project']
    assert c['conversation'] == [{**m, 'source_id': f'turn-{i}'} for i, m in enumerate(messages)]
    assert c['evidence'][0]['content'] == '已核验记录'
    assert project == before


def test_report_uses_complete_user_history_instead_of_model_risk_summary():
    from copy import deepcopy
    project = {'_report_requested': True, 'risks': '维护现金尚未明确', 'risks_source': 'model',
               'pending_patch': {'risks': '维护现金仍未知', 'budget_requested': 5000}}
    before = deepcopy(project)
    messages = [{'role': 'user', 'content': '现金订阅固定500元，维护由内部技术承担，不另付现金。'}]
    c = model_context(project, {}, [], messages)
    assert 'risks' not in c['project'] and 'risks' not in c['project']['pending_patch']
    assert c['conversation'] == [{**m, 'source_id': f'turn-{i}'} for i, m in enumerate(messages)]
    assert c['project']['pending_patch']['budget_requested'] == 5000
    assert project == before
    for origin in ('user', 'unknown'):
        manual = {**project, 'risks_source': origin, 'pending_patch': {}}
        assert model_context(manual, {}, [], messages)['project']['risks'] == project['risks']
    long = [{'role': 'user', 'content': '早期风险' * 10000}] + messages
    assert model_context(project, {}, [], long)['project']['risks'] == project['risks']
