"""Test all implemented collectors in an isolated server audit database."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import json
import platform
import time
from pathlib import Path

from sabc.catalog import SOURCES
from sabc.local_sources import REGIONS
from sabc.sources import SUPPORTED, collect
from sabc.store import Store, utcnow


CASES=[
    ('web','公开网页搜索','Go 1.26 release notes'),
    ('worldbank','人口指标','CHN/SP.POP.TOTL'),
    ('github','公开仓库','fastapi/fastapi'),
    ('sec','公司披露索引','320193'),
    ('sec','公司财务指标','320193/facts'),
    ('apple','应用搜索','us/notion'),
    ('stats','官方统计文章','https://www.stats.gov.cn/sj/zxfb/202608/t20260817_1965056.html'),
    ('miit','软件业统计文章','https://wap.miit.gov.cn/jgsj/yxj/xxfb/art/2026/art_7ecee3ca8eaa489685c7162a18a92fef.html'),
    ('cninfo','公告PDF','https://static.cninfo.com.cn/finalpage/2025-03-31/1222946119.PDF'),
    ('law','法规检索','个人信息保护法'),
    ('law','法规PDF全文','id:ff8081817b6472a3017b656cc2040044'),
    ('trends','热门搜索RSS','US'),
]+[('local',r['name'],r['example']) for r in REGIONS if r.get('example')]


def probe_case(store,case,collector=collect):
    source,name,query=case
    result=dict(source=source,name=name,query=query,checked_at=utcnow())
    started=time.monotonic()
    try:
        evidence=collector(store,'server-network-verification',source,query)
        result.update(status='success',title=evidence['title'],period=evidence['data_period'],
                      locator=evidence['source_locator'],evidence_id=evidence['id'])
    except Exception as error:
        result.update(status='failed',error=type(error).__name__+': '+str(error)[:500])
    result['elapsed_seconds']=round(time.monotonic()-started,2)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',help='Comma-separated source IDs; default: all implemented sources')
    parser.add_argument('--output',default='all-source-results')
    args=parser.parse_args()
    cases=CASES
    if args.sources:
        selected=set(args.sources.split(','))
        if selected-SUPPORTED: parser.error('Unknown sources: '+','.join(sorted(selected-SUPPORTED)))
        cases=[c for c in cases if c[0] in selected]
    output=Path(args.output)/time.strftime('%Y%m%d-%H%M%S')
    output.mkdir(parents=True,exist_ok=False)
    store=Store(output/'verification.db')
    report=dict(started_at=utcnow(),platform=platform.platform(),total=len(cases),
                scope='Known example queries for all implemented collectors; not complete platform coverage',
                not_implemented=[{'source':s[0],'name':s[1]} for s in SOURCES if s[0] not in SUPPORTED],
                results=[])
    print('RESULT_DIRECTORY '+str(output.resolve()),flush=True)
    # Two workers limit load while slow sources do not hold up every other source.
    with (output/'results.jsonl').open('w',encoding='utf-8') as stream, ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(probe_case,store,case) for case in cases]
        for future in as_completed(futures):
            result=future.result()
            report['results'].append(result)
            stream.write(json.dumps(result,ensure_ascii=False)+'\n');stream.flush()
            print(f"[{len(report['results'])}/{len(cases)}] {result['source']} {result['name']} {result['status']} {result['elapsed_seconds']}s {result.get('error','')}",flush=True)
    report.update(finished_at=utcnow(),passed=sum(r['status']=='success' for r in report['results']))
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (output/'summary.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['source','name','status','elapsed_seconds','title','period','query','error'],extrasaction='ignore')
        writer.writeheader();writer.writerows(report['results'])
    print(f"FINISHED PASS {report['passed']}/{report['total']}",flush=True)
    return 0 if report['passed']==report['total'] else 1


if __name__=='__main__':
    raise SystemExit(main())
