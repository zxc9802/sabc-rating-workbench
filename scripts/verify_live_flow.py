"""Explicit live acceptance run. Uses real APIs/model, synthetic company facts."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
import sabc.app as backend
from sabc.store import Store
from tests.test_rating import case


def main():
    backend.store=Store(Path('data/live-acceptance.db'))
    config=Store(Path('data/sabc.db')).get('settings','model')
    if not config: raise SystemExit('Configure a model first')
    backend.store.save('settings',config)
    client=TestClient(backend.app)
    def call(path,body):
        r=client.post(path,json=body)
        if r.status_code!=200: raise RuntimeError(f'{path}: HTTP {r.status_code}: {r.text[:200]}')
        return r.json()
    p,c,_,_=case(1)
    p.update(name='端到端验收：AI客服（测试素材，非真实公司）',project_type='internal',description='对重复咨询提供辅助草稿，由人工确认发送；先做内部试点。',target_user='本公司客服',business_goal='减少重复咨询处理时间',value_mechanism='释放客服产能用于复杂咨询，不直接认定裁员节省',success_metric='4周内重复咨询处理耗时下降20%，错误率不超过现状',timeframe='4周',risks='模型错误和敏感数据泄露，人工审核且数据脱敏',budget_requested=10000)
    c.update(name='验收测试公司（非真实）',strategy='提高服务效率，保持现金安全',team='客服负责人1人、工程师1人，每周合计20小时',capabilities='测试假设：已有客服系统，无本项目量化试点',approved_by='自动化验收素材')
    r=client.put('/api/company',json=c);r.raise_for_status()
    project=call('/api/projects',p);pid=project['id']
    evidence=call(f'/api/projects/{pid}/sources/github',{'query':'fastapi/fastapi'})
    print('Real source saved',evidence['id'],flush=True)
    first=call(f'/api/projects/{pid}/chat',{'message':'以上均为测试案例。请根据已知结构化资料生成可审查的八维评分建议、关键假设及至少3条正反理由。没有试点数据的判断明确标注假设，不能声称已验证。'})
    print('Model response received, proposal:',bool(first.get('proposal')),flush=True)
    if not first.get('proposal'): raise RuntimeError('Model did not produce a reviewable proposal; inspect interview')
    # The acceptance script explicitly reviews the proposed extraction for this synthetic case.
    patch=first.get('project_patch',{})
    if patch:
        r=client.patch(f'/api/projects/{pid}',json=patch);r.raise_for_status()
    initial=call(f'/api/projects/{pid}/assess',{'proposal':first['proposal'],'confirmed':True})
    assert initial['result']['grade'] in ('B','C','NR'), 'Unverified evidence cannot support A/S'
    negative=call(f'/api/projects/{pid}/evidence',{'title':'验收反方事实（测试）','source_locator':'test-fixture:resource-change','content':'仅用于验收：工程师已经调离，该4周周期内无替代人力，现有方案无法落地。','source_type':'internal','data_period':'2026-09','scope':'本测试项目','verification_status':'verified','level':1})
    second=call(f'/api/projects/{pid}/chat',{'message':f'新增已确认的测试反方事实见证据 {negative["id"]}：工程师调离，4周内无替代人力。请重新检查资源可行性，更新评分建议与反方意见，不保留旧的乐观判断。'})
    if not second.get('proposal'): raise RuntimeError('Reassessment proposal missing')
    if second.get('project_patch'):
        r=client.patch(f'/api/projects/{pid}',json=second['project_patch']);r.raise_for_status()
    revised=call(f'/api/projects/{pid}/assess',{'proposal':second['proposal'],'confirmed':True})
    old=client.get(f'/api/assessments/{initial["id"]}/export').json()
    assert old['result']==initial['result']
    summary={'test_only':True,'project_id':pid,'initial':initial['result'],'revised':revised['result'],'first_model_reply':first['reply'],'second_model_reply':second['reply'],'history_preserved':True,'note':'Real API and model calls; synthetic company facts. Not a business accuracy benchmark.'}
    Path('data/live-acceptance-result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Initial:',initial['result']['grade'],'Revised:',revised['result']['grade'],'History preserved',flush=True)


if __name__=='__main__': main()
