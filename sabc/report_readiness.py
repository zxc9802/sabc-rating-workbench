"""Bind completed information collection to the inputs accepted for generation."""
import hashlib
import json
from sabc.business_time import today
from sabc.rating import PROJECT_FIELDS, RULE_VERSION
from sabc.lifecycle import collection_ready


def fingerprint(project, company, evidence):
    effective={**project, **project.get('pending_patch', {})}
    life=project.get('lifecycle', {})
    inputs={
        'project':{k:effective.get(k) for k in set(PROJECT_FIELDS)|{'description','budget_requested','data_period','decision_facts','report_revision'}},
        'answers':[m for m in project.get('messages', []) if m.get('role')=='user'],
        'lifecycle':{k:life.get(k) for k in ('stage','mode','coverage','plan','draft_plan')},
        'company':company, 'evidence':sorted(evidence,key=lambda e:e['id']),
        'rule_version':RULE_VERSION, 'collection_version': 4, 'framing':project.get('framing'),
        'expired_evidence':sorted(e['id'] for e in evidence if e.get('valid_until') and e['valid_until']<today().isoformat()),
    }
    if 'risks_source' in project:
        inputs['project']['risks_source'] = project['risks_source']
    return hashlib.sha256(json.dumps(inputs,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def ready(project, company, evidence):
    saved=project.get('collection_completion') or {}
    return bool(not project.get('interview', {}).get('questions')
                and collection_ready(project.get('lifecycle', {}))
                and saved.get('collection_version')==4
                and saved.get('input_fingerprint')==fingerprint(project,company,evidence))
