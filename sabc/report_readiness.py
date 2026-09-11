"""Bind interview review approval to the exact inputs used for the report."""
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


def reviewed(project, company, evidence):
    review=project.get('assessment_review') or {}
    return bool(review.get('approved') and not review.get('questions') and project.get('proposal')
                and review.get('revised_proposal')==project.get('proposal')
                and collection_ready(project.get('lifecycle', {}))
                and review.get('input_fingerprint')==fingerprint(project,company,evidence))


def ready(project, company, evidence):
    return reviewed(project,company,evidence) and not any(project.get(k)!=v for k,v in project.get('pending_patch',{}).items())
