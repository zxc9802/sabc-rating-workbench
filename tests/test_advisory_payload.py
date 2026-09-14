"""The compact model input must preserve the complete source and report contract."""
from copy import deepcopy
import json
import pytest
from sabc import advisory
from tests.test_rating import case
from tests.report_fixtures import draft_reply
from tests.test_hidden_review import accepted


def expand(wire):
    # Independent JSON-pointer decoder used only to prove lossless serialization.
    def decode(value, visited=()):
        if isinstance(value, dict):
            if set(value) == {'$ref'}:
                path = value['$ref']
                assert path not in visited, 'cyclic reference'
                target = wire
                for key in path.removeprefix('/').split('/'):
                    target = target[int(key)] if isinstance(target, list) else target[key]
                return decode(target, visited + (path,))
            return {key: decode(item, visited) for key, item in value.items()}
        if isinstance(value, list):
            return [decode(item, visited) for item in value]
        return value
    return decode(wire)


def context():
    import sabc.app as app
    p, c, e, _ = case()
    description = '依据现状：这是已有商业收入的对外收费产品，原始经营资料仍需核对。' * 5
    p.update(id='payload-case', description=description,
             messages=[{'role':'user','content':description},
                       {'role':'assistant','content':'利润是否已经核算？'},
                       {'role':'user','content':'收入仍有，但独立利润尚未取得，不能把收入当利润。' * 5}],
             lifecycle={**app.lifecycle.initial(), 'coverage':draft_reply()['dimension_coverage']})
    p['lifecycle']['review']={'conclusion':'needs_info','summary':'仍需核对真实经营回报。' * 10,
                              'next_action':'取得原始财务资料。' * 10,'next_review_days':14}
    proposal=draft_reply()['proposal']
    proposal['dimensions']['market']['reason']='该商业产品的客户需求和付费意愿仍需依据实际经营记录核查。' * 6
    proposal['pros']=['已有客户群和商业化基础。' * 10]
    proposal['cons']=['付费意愿及经营回报仍需核对。' * 10]
    candidate=app.build_assessment(p,c,e,proposal)
    # Use the actual candidate snapshot after the program computes the report.
    packet=advisory.packet('report',candidate['snapshot']['project'],c,e,candidate)
    packet.update(previous_findings=[],previous_changes={})
    return packet


def test_compact_report_round_trips_without_mutating_saved_context():
    original=context();before=deepcopy(original)
    wire=advisory.compact_context(original)
    assert original==before and expand(wire)==original
    assert wire['sources']['turn-0']=={'$ref':'/sources/description'}
    assert wire['conversation'][0]['content']=={'$ref':'/sources/turn-0'}
    assert wire['project']['description']=={'$ref':'/sources/description'}
    assert wire['project']['lifecycle']['review']=={'$ref':'/candidate/review'}
    assert wire['candidate']['result']['pros']=={'$ref':'/candidate/proposal/pros'}
    assert wire['candidate']['result']['dimensions'][1]['reason']=={'$ref':'/candidate/proposal/dimensions/market/reason'}
    assert len(json.dumps(wire,ensure_ascii=False)) < len(json.dumps(original,ensure_ascii=False))


def test_dedup_preserves_conflicts_unknowns_roles_and_source_identifiers():
    original=context()
    original['conversation'].append({'id':'turn-3','role':'assistant','content':original['sources']['turn-2']})
    original['candidate']['result']['pros']=['程序计算后与建议不同的结论。' * 6]
    dimension=original['candidate']['result']['dimensions'][1]
    dimension.update(score=None,basis='unknown',reason='经核对尚不能判断，保留未知。' * 6)
    wire=advisory.compact_context(original)
    assert expand(wire)==original
    assert set(wire['sources'])==set(original['sources']) and 'turn-3' not in wire['sources']
    assert [(m['id'],m['role']) for m in wire['conversation']]==[(m['id'],m['role']) for m in original['conversation']]
    assert wire['candidate']['result']['dimensions'][1]==dimension
    assert wire['candidate']['result']['pros']==original['candidate']['result']['pros']
    assert wire['conversation'][-1]['content']==original['sources']['turn-2']


def test_empty_and_collection_contexts_stay_lossless():
    assert advisory.compact_context({})=={}
    original=advisory.packet('collection',{'description':'短描述','messages':[
        {'role':'user','content':'短描述'},{'role':'user','content':'同一句回答。' * 25},
        {'role':'user','content':'同一句回答。' * 25}]}, {}, [], None)
    wire=advisory.compact_context(original)
    assert expand(wire)==original and wire['candidate'] is None
    assert wire['sources']['turn-0']=='短描述'  # A reference would be larger.
    assert wire['sources']['turn-2']=={'$ref':'/sources/turn-1'}
    assert set(wire['sources'])==set(original['sources'])


def test_network_gets_compact_input_but_validation_matches_original_user_quote(monkeypatch):
    original=context();before=deepcopy(original);seen=[]
    quote=original['sources']['turn-2']
    response=accepted()
    response.update(checks={**response['checks'],'facts':'revise'},project_patch={'risks':'独立利润未取得'},
                    findings=[{'perspective':'facts','target':'risks','source_id':'turn-2','quote':quote,'reason':'原文限定必须保留'}],
                    framing={'project_type':'growth','business_stage':'operating','purpose':'unknown',
                             'quotes':{'project_type':original['sources']['description'],'business_stage':original['sources']['description']}})
    def completion(client,url,payload,headers,timeout):
        seen.append(deepcopy(payload))
        wire=json.loads(payload['messages'][1]['content'])
        assert expand(wire)==original
        assert isinstance(wire['conversation'][0]['content'],dict)
        if len(seen)==1:return '{"checks":{}}'  # Trigger the existing format retry.
        return json.dumps(response,ensure_ascii=False)
    monkeypatch.setattr(advisory,'completion',completion)
    monkeypatch.setattr(advisory,'routed',lambda role,settings,execute:execute({
        'model':'test','base_url':'https://model.example/v1','key':'test','primary':True}))
    result=advisory._request({},'',original)
    assert len(seen)==2 and seen[0]['messages'][1]==seen[1]['messages'][1]
    assert advisory.REFERENCE_PROMPT in seen[0]['messages'][0]['content']
    assert result['findings'][0]['quote']==quote and result['framing']['project_type']=='growth'
    assert original==before


def test_reference_objects_cannot_be_saved_as_corrected_facts():
    original=context();response=accepted()
    response['project_patch']={'risks':{'$ref':'/sources/turn-2'}}
    with pytest.raises(ValueError,match='不能返回输入引用对象'):
        advisory.validate(response,original)


def test_second_review_references_identical_revision_and_keeps_findings():
    original=context()
    original['previous_findings']=[{'source_id':'turn-2','quote':original['sources']['turn-2'],'reason':'错误地把收入当利润'}]
    original['previous_changes']={'proposal':deepcopy(original['candidate']['proposal'])}
    wire=advisory.compact_context(original)
    assert expand(wire)==original
    assert wire['previous_findings']==original['previous_findings']
    assert wire['previous_changes']['proposal']=={'$ref':'/candidate/proposal'}
    original['previous_changes']['proposal']['dimensions']['market']['reason']='上一轮的不同理由仍需保留'
    wire=advisory.compact_context(original)
    assert expand(wire)==original
    assert wire['previous_changes']==original['previous_changes']


def test_short_request_does_not_grow_due_to_reference_instructions(monkeypatch):
    original={'sources':{'description':'简短项目描述','turn-0':'简短项目描述'}}
    def completion(client,url,payload,headers,timeout):
        assert json.loads(payload['messages'][1]['content'])==original
        assert advisory.REFERENCE_PROMPT not in payload['messages'][0]['content']
        return '{}'
    monkeypatch.setattr(advisory,'completion',completion)
    monkeypatch.setattr(advisory,'validate',lambda value,context:accepted())
    monkeypatch.setattr(advisory,'routed',lambda role,settings,execute:execute({
        'model':'test','base_url':'https://model.example/v1','key':'test','primary':True}))
    assert advisory._request({},'',original)['checks']['facts']=='pass'
