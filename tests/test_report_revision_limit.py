"""Four modifications across drafting and review; deliver version five without re-review."""
from copy import deepcopy
import json
import httpx
import pytest

from sabc import llm, report_grounding
from sabc.model_output import ModelResponseError
from sabc.report_corrections import ReportCorrections
from tests.test_report_timeouts import report_input
from tests.test_report_generation import prepare, send, accepted, client
from tests.report_fixtures import REPORT_DESCRIPTION, grounded_proposal


@pytest.fixture(autouse=True)
def isolated_providers(monkeypatch):
    for key in ('SABC_MIXTOKEN_API_KEY','SABC_FAL_API_KEY','SABC_DEEPSEEK_API_KEY'):
        monkeypatch.delenv(key,raising=False)


def test_fifth_draft_skips_content_validation_even_if_issue_remains(monkeypatch):
    project, company, evidence, reply = report_input()
    reply['proposal']['assessment_scope']['quote'] = '未出现在用户原话中的范围'
    calls = []; checks = []; budget = ReportCorrections()
    validate = report_grounding.validate
    def check(*args, **kwargs):
        checks.append(1)
        return validate(*args, **kwargs)
    def completion(client, url, payload, headers, remaining):
        calls.append(payload['model'])
        return json.dumps(reply)
    monkeypatch.setattr(llm, 'completion', completion)
    monkeypatch.setattr(report_grounding, 'validate', check)
    result = llm.analyze({'base_url':'https://model.example','model':'test','report_corrections':budget},
                         '', project, company, evidence, [])
    assert result['proposal']['assessment_scope']['quote'] == reply['proposal']['assessment_scope']['quote']
    assert calls == ['test'] * 5 and len(checks) == 4 and budget.count == 4


@pytest.mark.parametrize('broken', ['json', 'reference'])
def test_fifth_draft_must_still_be_readable_with_valid_references(monkeypatch, broken):
    project, company, evidence, reply = report_input()
    reply['proposal']['dimensions']['risk']['evidence_ids'] = ['nonexistent']
    calls = []
    def completion(client, url, payload, headers, remaining):
        calls.append(payload['model'])
        return '{' if broken == 'json' else json.dumps(reply)
    monkeypatch.setattr(llm, 'completion', completion)
    monkeypatch.setenv('SABC_DEEPSEEK_API_KEY','synthetic-backup')
    with pytest.raises(ModelResponseError):
        llm.analyze({'base_url':'https://model.example','model':'test'},'',project,company,evidence,[])
    assert calls == ['test'] * 5


def test_provider_failure_does_not_reset_revision_count(monkeypatch):
    project, company, evidence, reply = report_input()
    reply['proposal']['assessment_scope']['quote'] = '需要修改的范围'
    calls = []; budget = ReportCorrections()
    def completion(client, url, payload, headers, remaining):
        calls.append(payload['model'])
        if len(calls) == 3:
            raise httpx.ReadTimeout('upstream timeout')
        return json.dumps(reply)
    monkeypatch.setattr(llm, 'completion', completion)
    monkeypatch.setenv('SABC_DEEPSEEK_API_KEY','synthetic-backup')
    assert llm.analyze({'base_url':'https://model.example','model':'test','report_corrections':budget},
                       '',project,company,evidence,[])['proposal']
    assert calls == ['test'] * 3 + ['deepseek-flash'] * 3
    assert budget.count == 4


@pytest.mark.parametrize('draft_corrections', [2, 4])
def test_draft_and_review_share_four_modifications(client, monkeypatch, draft_corrections):
    module, advisory, url, calls = prepare(client, monkeypatch)
    client.patch(url, json={'description':REPORT_DESCRIPTION})
    interview = module.analyze
    draft_calls = []; reviews = []
    def analyze(*args):
        return llm.analyze(*args) if args[2].get('_report_requested') else interview(*args)
    def completion(client, endpoint, payload, headers, remaining):
        draft_calls.append(payload['model'])
        reply = interview({}, '', {'_report_requested':True})
        reply['proposal'] = grounded_proposal(reply['proposal'], REPORT_DESCRIPTION, 'description')
        if draft_corrections == 4:
            reply['proposal']['assessment_scope']['quote'] = '第五版仍未匹配的引用'
        elif len(draft_calls) < 3:
            reply['proposal']['dimensions']['risk']['reason'] = ''
        return json.dumps(reply)
    def review(settings, key, context):
        reviews.append(deepcopy(context))
        result = accepted()
        result.update(checks={**result['checks'],'facts':'revise'},
                      project_patch={'risks':f'修订后的风险说明{len(reviews)}'}, findings=[{'reason':'修订'}])
        return result
    monkeypatch.setattr(module,'analyze',analyze)
    monkeypatch.setattr(llm,'completion',completion)
    monkeypatch.setattr(advisory,'_request',review)
    response = send(client,url)
    assert response.status_code == 200, response.text
    quality = client.get(url).json()['assessments'][0]['snapshot']['quality_review']
    assert len(draft_calls) == draft_corrections + 1 and len(reviews) == 4 - draft_corrections
    if reviews:
        assert reviews[-1]['final_revision'] is True
    assert quality['corrections'] == 4 and quality['status'] == 'revision_limit'


def test_final_review_revision_does_not_run_content_validator(monkeypatch):
    from sabc import advisory
    from tests.test_advisory_payload import context
    packet = context()
    packet['final_revision'] = True
    reply = accepted()
    reply['proposal'] = deepcopy(packet['candidate']['proposal'])
    reply['proposal']['assessment_scope'] = {'subject':'本项目','level':'project',
                                           'source_id':'description','quote':'最终版本不再核查原文匹配'}
    monkeypatch.setattr(advisory,'completion',lambda *args:json.dumps(reply))
    def unexpected_check(*args):
        pytest.fail('final revision must not run another content validation')
    monkeypatch.setattr(advisory,'validate',unexpected_check)
    result = advisory._request({'base_url':'https://model.example','model':'test',
                                'report_corrections':ReportCorrections({'count':3})},'',packet)
    assert result['proposal']['assessment_scope']['quote'] == reply['proposal']['assessment_scope']['quote']


def test_resume_preserves_remaining_review_modifications(client, monkeypatch):
    module, advisory, url, calls = prepare(client,monkeypatch)
    reviews = []; failed = False
    def review(settings, key, context):
        nonlocal failed
        if len(reviews) == 2 and not failed:
            failed = True
            raise httpx.ReadTimeout('interrupted')
        reviews.append(deepcopy(context))
        result = accepted()
        result.update(checks={**result['checks'],'facts':'revise'},
                      project_patch={'risks':f'第{len(reviews)}次修订'},findings=[{'reason':'修订'}])
        return result
    monkeypatch.setattr(advisory,'_request',review)
    assert send(client,url).status_code == 422
    saved = module.store.get('report_workflows',url.split('/')[-1])
    assert saved['corrections']['count'] == 2
    assert send(client,url,message='继续处理',generate_report=True).status_code == 200
    detail = client.get(url).json()
    assert len(reviews) == 4 and calls.count('draft') == 1
    assert detail['assessments'][0]['snapshot']['quality_review']['corrections'] == 4
    assert len(detail['assessments']) == 1
