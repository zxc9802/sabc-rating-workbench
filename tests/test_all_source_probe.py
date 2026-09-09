from scripts.probe_all_sources import CASES, probe_case
from sabc.sources import SUPPORTED, request_spec


def test_manifest_covers_all_implemented_sources():
    assert {c[0] for c in CASES}==SUPPORTED
    assert len([c for c in CASES if c[0]=='local'])==32
    for source,name,query in CASES:
        request_spec(source,query)


def test_collector_failure_is_recorded():
    def fail(*args): raise ValueError('连接失败')
    result=probe_case(None,('github','仓库','fastapi/fastapi'),collector=fail)
    assert result['status']=='failed' and '连接失败' in result['error']


def test_success_preserves_evidence_reference():
    def ok(*args):
        return {'id':'test','title':'仓库','data_period':'采集时点','source_locator':'https://api.github.com/repos/fastapi/fastapi'}
    result=probe_case(None,('github','仓库','fastapi/fastapi'),collector=ok)
    assert result['status']=='success' and result['evidence_id']=='test'
