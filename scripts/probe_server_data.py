"""Run production anonymous regional collectors from the deployment server."""
import argparse
import csv
import hashlib
import json
import platform
import time
from pathlib import Path

import httpx

from sabc.local_sources import REGIONS, fetch_local
from sabc.store import utcnow


def probe(item, attempt, timeout, fetcher=fetch_local):
    result=dict(region=item['id'],name=item.get('name',item['id']),query=item['example'],
                attempt=attempt,checked_at=utcnow(),retryable=False,requests=[])
    started=time.monotonic()
    def trace(response):
        result['requests'].append({'url':str(response.request.url),'status':response.status_code})
    try:
        # No proxy environment, saved cookies, browser session or application database.
        with httpx.Client(timeout=timeout,trust_env=False,follow_redirects=False,
                          event_hooks={'response':[trace]}) as client:
            data=fetcher(client,item['example'])
        rows=data['facts'].get('rows')
        if not isinstance(rows,list) or not rows or not all(isinstance(r,dict) and r for r in rows):
            raise ValueError('未取得有效数据记录')
        result.update(status='success',rows=len(rows),title=data['title'],
                      locator=data['locator'],period=data['period'],limitation=data['limitation'],
                      reported_total=data['facts'].get('reported_total'),
                      data_sha256=hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True).encode()).hexdigest())
    except httpx.HTTPStatusError as error:
        status=error.response.status_code
        result.update(status='http_error',http_status=status,error=f'HTTP {status}',
                      retryable=status in (500,502,503,504))
    except httpx.HTTPError as error:
        result.update(status='network_error',error=type(error).__name__+': '+str(error)[:300],
                      retryable=isinstance(error,(httpx.TimeoutException,httpx.ConnectError))
                      and not any(s in str(error).upper() for s in ('CERTIFICATE','SSL')))
    except ValueError as error:
        result.update(status='no_usable_data',error=str(error)[:500])
    except (KeyError,TypeError,AttributeError) as error:
        result.update(status='format_changed',error=type(error).__name__+': '+str(error)[:300])
    result['elapsed_seconds']=round(time.monotonic()-started,2)
    return result


def run_rounds(items,retries,timeout,probe_fn=probe):
    pending=list(items)
    for attempt in range(1,retries+2):
        retry=[]
        for item in pending:
            result=probe_fn(item,attempt,timeout)
            yield result
            if result['retryable']: retry.append(item)
        pending=retry
        if not pending: break


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--regions',help='Comma-separated region IDs; default: all integrated regions')
    parser.add_argument('--timeout',type=float,default=15,help='Per HTTP operation timeout in seconds')
    parser.add_argument('--retries',type=int,choices=range(4),default=3)
    parser.add_argument('--output',default='server-probe-results')
    args=parser.parse_args()
    if not 1<=args.timeout<=120: parser.error('--timeout must be between 1 and 120')
    regions=[r for r in REGIONS if r.get('example')]
    if args.regions:
        selected=set(args.regions.split(','))
        unknown=selected-{r['id'] for r in regions}
        if unknown: parser.error('Unknown or not integrated: '+','.join(sorted(unknown)))
        regions=[r for r in regions if r['id'] in selected]
    output=Path(args.output)/time.strftime('%Y%m%d-%H%M%S')
    output.mkdir(parents=True,exist_ok=False)
    report={'started_at':utcnow(),'platform':platform.platform(),'python':platform.python_version(),
            'scope':'Selected production collectors; actual public preview records required',
            'network':'Direct connection; environment proxies disabled; TLS verification enabled',
            'not_integrated':[{'region':r['id'],'name':r['name']} for r in REGIONS if not r.get('example')],
            'results':[]}
    latest={}
    with (output/'attempts.jsonl').open('w',encoding='utf-8') as stream:
        for result in run_rounds(regions,args.retries,args.timeout):
            stream.write(json.dumps(result,ensure_ascii=False)+'\n');stream.flush()
            latest[result['region']]=result
            print(f"{result['region']:15} attempt={result['attempt']} {result['status']} rows={result.get('rows',0)} {result.get('error','')}",flush=True)
    report.update(finished_at=utcnow(),results=list(latest.values()))
    report['passed']=sum(r['status']=='success' for r in latest.values())
    report['total']=len(regions)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (output/'summary.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['region','name','status','rows','title','period','elapsed_seconds','error'],extrasaction='ignore')
        writer.writeheader();writer.writerows(latest.values())
    print(f"PASS {report['passed']}/{report['total']}; reports: {output.resolve()}")
    return 0 if report['passed']==report['total'] else 1


if __name__=='__main__':
    raise SystemExit(main())
