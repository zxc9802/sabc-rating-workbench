"""Replay exported snapshots or labelled historical cases, without model calls."""
import argparse
from datetime import date
import json
from pathlib import Path

from sabc.rating import assess, RULE_VERSION
from sabc.schema import validate_proposal


def replay(cases, as_of):
    results=[]
    for index,case in enumerate(cases):
        snapshot=case.get('snapshot',case)
        name=case.get('name') or snapshot.get('project',{}).get('name') or str(index+1)
        try:
            args=[snapshot['project'],snapshot['company'],snapshot['evidence'],validate_proposal(snapshot['proposal'])]
            result=assess(*args,today=as_of)
            repeated=assess(*args,today=as_of)
            expected=case.get('expected_grade')
            if expected is not None and expected not in ('S','A','B','C','NR'): raise ValueError('expected_grade 无效')
            results.append({'name':name,'grade':result['grade'],'expected_grade':expected,'matches_expected':result['grade']==expected if expected is not None else None,'deterministic':result==repeated,'result':result})
        except (ValueError,KeyError,TypeError) as error:
            results.append({'name':name,'error':str(error)})
    labelled=[r for r in results if r.get('expected_grade') is not None and 'error' not in r]
    return {'rule_version':RULE_VERSION,'as_of':as_of.isoformat(),'count':len(results),'errors':sum('error' in r for r in results),'labelled_count':len(labelled),'agreement_rate':sum(r['matches_expected'] for r in labelled)/len(labelled) if labelled else None,'note':'一致率只比较人工预期等级，不代表经营成功预测准确率；未标注样本不计入。','cases':results}


def main():
    parser=argparse.ArgumentParser(description='重放评级快照或历史案例 JSON')
    parser.add_argument('input',type=Path)
    parser.add_argument('--as-of',required=True,type=date.fromisoformat,help='固定证据时效判断日期 YYYY-MM-DD')
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    data=json.loads(args.input.read_text(encoding='utf-8-sig'))
    cases=data if isinstance(data,list) else [data]
    result=replay(cases,args.as_of)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"{result['count']} cases, {result['errors']} errors; output: {args.output}")
    raise SystemExit(1 if result['errors'] else 0)


if __name__=='__main__': main()
