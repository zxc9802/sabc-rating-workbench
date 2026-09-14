from copy import deepcopy
import pytest
from tests.test_app import client
from tests.report_fixtures import draft_reply
from tests.test_rating import case


def accepted():
    return {'checks': {k: 'pass' for k in ('facts', 'business', 'risk', 'consistency')},
            'findings': [], 'project_patch': {}, 'coverage_reasons': {}, 'framing': None,
            'questions': [], 'proposal': None, 'stage_review': None}


def test_new_project_does_not_silently_choose_growth(client):
    p = client.post('/api/projects', json={'name': '内部工具', 'description': '给自己客服使用'}).json()
    assert p['project_type'] is None


def test_public_research_has_no_approval_action(client):
    import sabc.app as module
    p, c, _, proposal = case()
    proposal['dimensions']['return'].update(score=None, basis='unknown')
    client.put('/api/company', json=c)
    pid = client.post('/api/projects', json=p).json()['id']
    saved = module.store.get('projects', pid)
    saved['framing'] = {'business_stage': 'operating', 'purpose': 'research'}
    saved['lifecycle']['review'] = {'conclusion': 'needs_info', 'summary': '待补资料', 'next_action': '不批准投入'}
    module.store.save('projects', saved)
    report = client.post(f'/api/projects/{pid}/assess', json={'proposal': proposal, 'confirmed': True}).json()
    assert report['result']['business_stage'] == 'operating'
    assert '批准' not in report['snapshot']['project']['lifecycle']['review']['next_action']


def test_review_uses_current_facts_without_stale_report_summary():
    from sabc import advisory
    p, c, e, _ = case()
    p.update(description='尚未取得对照案例', messages=[{'role': 'assistant', 'content': '对照案例不存在'}],
             pending_patch={'business_goal': '仅研究继续经营条件'})
    p['lifecycle'] = {'coverage': {'opportunity': {}}, 'review': {'summary': '旧报告的错误总结'}, 'reviews': [{'summary': '旧版本'}]}
    context = advisory.packet('collection', p, c, e, None)
    assert context['project']['business_goal'] == '仅研究继续经营条件'
    assert 'review' not in context['project']['lifecycle']
    assert 'reviews' not in context['project']['lifecycle']
    assert 'turn-0' not in context['sources']
    result = accepted()
    result.update(checks={**result['checks'], 'facts': 'revise'}, coverage_reasons={'opportunity': '尚未取得对照案例'},
                  findings=[{'perspective': 'facts', 'target': 'coverage.opportunity.reason',
                             'source_id': 'turn-0', 'quote': '对照案例不存在', 'reason': '不能引用模型发言证明事实'}])
    with pytest.raises(ValueError, match='实际来源'):
        advisory.validate(result, context)
    result['findings'][0].update(source_id='description', quote='尚未取得对照案例')
    assert advisory.validate(result, context)['coverage_reasons']['opportunity'] == '尚未取得对照案例'


def test_unknown_source_cannot_pass_as_nonexistent_case():
    from sabc import advisory
    p, c, e, _ = case()
    p.update(description='现有材料中没有对照案例', lifecycle={'coverage': {'opportunity': {
        'status': 'unknown', 'reason': '同规模的对照案例不存在。',
        'items': {'comparison': {'status': 'unknown', 'quote': '现有材料中没有对照案例'}}}}})
    context = advisory.packet('collection', p, c, e, None)
    with pytest.raises(ValueError, match='客观不存在'):
        advisory.validate(accepted(), context)
    for reason in ('尚未取得同规模对照案例。', '现有材料没有对照案例，但不能说案例不存在。'):
        p['lifecycle']['coverage']['opportunity']['reason'] = reason
        assert not advisory.packet('collection', p, c, e, None)['source_limit_flags']


def test_review_cannot_pass_a_commercial_product_using_internal_market_rubric():
    from sabc import advisory
    import sabc.app as module
    p, c, e, proposal = case()
    proposal = draft_reply()['proposal']
    p['id'] = 'rubric-regression'
    proposal['dimensions']['market'].update(score=4, reason='内需型内部效率与工具需求，不适用外部市场规模')
    candidate = module.build_assessment(p, c, e, proposal)
    context = advisory.packet('report', p, c, e, candidate)
    assert context['rule_issues']
    with pytest.raises(ValueError, match='评分理由'):
        advisory.validate(accepted(), context)


def test_review_restores_unknown_status_without_changing_source_or_verification(monkeypatch):
    from sabc import advisory
    p, c, e, _ = case()
    p.update(description='同类项目的可迁移案例尚未取得', lifecycle={'stage':'pre','coverage': deepcopy(draft_reply()['dimension_coverage'])})
    item = p['lifecycle']['coverage']['return']['items']['validation_transfer']
    item['quote'] = p['description']
    calls = []
    def request(settings, key, context):
        calls.append(context)
        result = accepted()
        if len(calls) == 1:
            result.update(checks={**result['checks'], 'facts': 'revise'},
                          coverage_statuses={'return': {'validation_transfer': 'unknown'}},
                          findings=[{'perspective': 'facts', 'target': 'return.validation_transfer',
                                     'source_id': 'description', 'quote': p['description'], 'reason': '未取得被误记为已知'}])
        return advisory.validate(result, context)
    monkeypatch.setattr(advisory, '_request', request)
    import sabc.app as module
    p['id']='unknown-restoration'
    candidate=module.build_assessment(p,c,e,draft_reply()['proposal'])
    updated=advisory.review_report({}, '', candidate, module.build_assessment)['snapshot']['project']
    corrected = updated['lifecycle']['coverage']['return']['items']['validation_transfer']
    assert corrected == {**item, 'status': 'unknown'}
    assert calls[1]['project']['lifecycle']['coverage']['return']['status'] == 'unknown'
    assert item['status'] == 'known'


def test_report_reviewer_may_echo_classification_but_changes_need_findings():
    from sabc import advisory
    import sabc.app as module
    p, c, e, _ = case()
    p.update(id='framing-echo', description='本次是已商业化产品的外部资料研究',
             framing={'project_type': 'growth', 'business_stage': 'operating', 'purpose': 'research',
                      'quotes': {k: '本次是已商业化产品的外部资料研究' for k in ('project_type', 'business_stage', 'purpose')}})
    candidate = module.build_assessment(p, c, e, draft_reply()['proposal'])
    context = advisory.packet('report', p, c, e, candidate)
    result = {**accepted(), 'framing': deepcopy(p['framing'])}
    assert advisory.validate(result, context)['framing'] is None
    result['framing']['purpose'] = 'expand'
    with pytest.raises(ValueError, match='须说明'):
        advisory.validate(result, context)


@pytest.mark.parametrize('status', ['unknown', 'external', 'future'])
def test_review_cannot_reask_unavailable_information(status):
    from sabc import advisory
    p, c, e, _ = case()
    p.update(description='最多能承受的损失未知', lifecycle={'coverage': {'cash': {'items': {'max_loss': {'status': status}}}}})
    context = advisory.packet('collection', p, c, e, None)
    result = accepted()
    result.update(checks={**result['checks'], 'risk': 'needs_answer'},
                  findings=[{'perspective': 'risk', 'target': 'cash.max_loss', 'source_id': 'description',
                             'quote': p['description'], 'reason': '缺少损失上限'}],
                  questions=[{'dimension': 'cash', 'checkpoint': 'max_loss', 'question': '最多能承受多少损失？',
                              'source_id': 'description', 'quote': p['description']}])
    with pytest.raises(ValueError, match='无法提供'):
        advisory.validate(result, context)




def test_review_failover_shares_total_deadline(monkeypatch):
    from sabc import advisory
    clock=[0.0];timeouts=[]
    monkeypatch.setattr(advisory.time,'monotonic',lambda:clock[0])
    def completion(client,url,payload,headers,timeout):
        timeouts.append(timeout)
        if len(timeouts)==1:
            clock[0]=60.0
            raise ValueError('first provider failed after 60 seconds')
        return '{}'
    def routed(role,settings,execute):
        route={'model':'test','base_url':'https://model.example/v1','key':'test','primary':False}
        try:return execute(route)
        except ValueError:return execute(route)
    monkeypatch.setattr(advisory,'completion',completion)
    monkeypatch.setattr(advisory,'routed',routed)
    monkeypatch.setattr(advisory,'validate',lambda value,context:accepted())
    assert advisory._request({},'',{})['checks']['facts']=='pass'
    assert timeouts==[90.0,30.0]
