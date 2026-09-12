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


def test_report_preserves_early_user_corrections_without_old_report_prose():
    messages = [{'role': 'user', 'content': '更正：ROAS只除广告费，净贡献还要扣代工和包材。'}]
    messages += [{'role': 'assistant', 'content': '旧口径草稿'}, {'role': 'user', 'content': '其他未知'}] * 20
    project = {'_report_requested': True, '_previous_stage_report': {
        'id': 'old', 'result': {'grade': 'B', 'dimensions': [{'key': 'return', 'score': 3, 'reason': '旧公式'}],
                             'validation_plan': [{'method': '净贡献=收入-广告费'}]}}}
    c = model_context(project, {}, [], messages)
    assert c['conversation'][0] == messages[0]
    assert all(m['role'] == 'user' for m in c['conversation'])
    assert c['project']['previous_stage_report']['grade'] == 'B'
    assert '旧公式' not in str(c) and '净贡献=收入-广告费' not in str(c)
    assert '旧口径草稿' not in str(c)


def test_report_user_history_is_bounded_and_latest_correction_kept():
    messages = [{'role': 'user', 'content': '旧资料' * 10000}, {'role': 'user', 'content': '最新总上限3万，损失1.5万。'}]
    c = model_context({'_report_requested': True}, {}, [], messages)
    assert sum(len(m['content']) for m in c['conversation']) == 24000
    assert c['conversation'][-1] == messages[-1]
    assert c['context_limits']['conversation_chars_truncated']
