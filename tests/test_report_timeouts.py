"""Long reports get more time; retries still consume a finite deadline."""
import json
from types import SimpleNamespace

import pytest
from sabc import advisory, llm
from tests.report_fixtures import draft_reply, grounded_proposal, REPORT_DESCRIPTION
from tests.test_advisory_payload import context as report_context
from tests.test_hidden_review import accepted
from tests.test_rating import case


@pytest.fixture
def clock(monkeypatch):
    now = [100.0]
    timer = SimpleNamespace(monotonic=lambda: now[0])
    monkeypatch.setattr(llm, 'time', timer)
    monkeypatch.setattr(advisory, 'time', timer)
    return now


def report_input():
    project, company, evidence, _ = case()
    project.update(description=REPORT_DESCRIPTION, _report_requested=True)
    reply = draft_reply()
    reply['proposal'] = grounded_proposal(reply['proposal'])
    return project, company, evidence, reply


@pytest.mark.parametrize('report,elapsed,budget', [(True, 180, 300), (False, 30, 90)])
def test_slow_response_can_be_corrected_with_remaining_time(monkeypatch, clock, report, elapsed, budget):
    project, company, evidence, reply = report_input()
    if not report:
        project.pop('_report_requested')
        reply = {'reply': '还有哪些费用？'}
    seen = []
    def completion(client, url, payload, headers, timeout):
        seen.append(timeout)
        if len(seen) == 1:
            clock[0] += elapsed
            return '{'
        assert len(payload['messages']) == 4  # The invalid response was rejected and corrected.
        return json.dumps(reply, ensure_ascii=False)
    monkeypatch.setattr(llm, 'completion', completion)
    result = llm._analyze({'base_url': 'https://model.example/v1', 'model': 'test'},
                          'test', project, company, evidence, [])
    assert result['mode'] == 'model'
    assert seen == [budget, budget - elapsed]
    assert bool(result['proposal']) is report


def test_report_correction_does_not_restart_expired_deadline(monkeypatch, clock):
    project, company, evidence, _ = report_input()
    seen = []
    def completion(client, url, payload, headers, timeout):
        seen.append(timeout)
        clock[0] += 301
        return '{'
    monkeypatch.setattr(llm, 'completion', completion)
    with pytest.raises(llm.ModelResponseError) as error:
        llm._analyze({'base_url': 'https://model.example/v1', 'model': 'test'},
                     'test', project, company, evidence, [])
    assert error.value.stage == 'response_json'
    assert seen == [300]


@pytest.mark.parametrize('mode,elapsed,budget', [('report', 180, 300), ('collection', 30, 90)])
def test_review_correction_uses_remaining_route_budget(monkeypatch, clock, mode, elapsed, budget):
    context = report_context() if mode == 'report' else advisory.packet(mode, {'lifecycle': {}}, {}, [], None)
    seen = []
    def completion(client, url, payload, headers, timeout):
        seen.append(timeout)
        if len(seen) == 1:
            clock[0] += elapsed
            return '{'
        return json.dumps(accepted())
    def routed(role, settings, execute):
        route = {'base_url': 'https://model.example/v1', 'model': 'test', 'key': '', 'primary': False,
                 'correction_deadline': clock[0] + budget}
        with pytest.raises(ValueError):
            execute(route)
        return execute(route)
    monkeypatch.setattr(advisory, 'completion', completion)
    monkeypatch.setattr(advisory, 'routed', routed)
    assert advisory._request({}, '', context)['checks']['facts'] == 'pass'
    assert seen == [budget, budget - elapsed]
