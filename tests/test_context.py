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
