"""Bind prepared interview judgments to the exact inputs used for the report."""
import hashlib
import json
from datetime import date
from sabc.rating import PROJECT_FIELDS, RULE_VERSION
from sabc.lifecycle import collection_ready


def fingerprint(project, company, evidence):
    effective={**project, **project.get('pending_patch', {})}
    life=project.get('lifecycle', {})
    inputs={
        'project':{k:effective.get(k) for k in set(PROJECT_FIELDS)|{'description','budget_requested'}},
        'answers':[m for m in project.get('messages', []) if m.get('role')=='user'],
        'lifecycle':{k:life.get(k) for k in ('stage','mode','coverage','plan','draft_plan')},
        'company':company, 'evidence':sorted(evidence,key=lambda e:e['id']),
        'rule_version':RULE_VERSION,
        'expired_evidence':sorted(e['id'] for e in evidence if e.get('valid_until') and e['valid_until']<date.today().isoformat()),
    }
    return hashlib.sha256(json.dumps(inputs,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def prepared(project, company, evidence):
    saved=project.get('report_preparation') or {}
    # Existing report-ready projects retain their saved judgment without another model call.
    legacy=project.get('assessment_review') or {}
    expected=saved.get('proposal') if saved else legacy.get('revised_proposal')
    stamp=saved.get('input_fingerprint') if saved else legacy.get('input_fingerprint')
    return bool(project.get('proposal') and expected==project['proposal']
                and collection_ready(project.get('lifecycle', {}))
                and stamp==fingerprint(project,company,evidence))


def ready(project, company, evidence):
    return prepared(project,company,evidence) and not any(project.get(k)!=v for k,v in project.get('pending_patch',{}).items())
