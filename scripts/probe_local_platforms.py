"""Audit known public platform candidates; HTTP 200 never means data is integrated."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import httpx


def probe(item, attempt):
    result={**item,'attempt':attempt,'checked_at':datetime.now(timezone.utc).isoformat()}
    url=item['url']
    try:
        with httpx.Client(timeout=10,trust_env=False,follow_redirects=False) as client:
            response=client.get(url)
        result.update(http_status=response.status_code,retryable=response.status_code in (500,502,503,504))
        if response.is_redirect:
            target=urljoin(url,response.headers.get('location',''))
            result.update(status='redirect_unverified',redirect=target)
            if any(word in urlparse(target).path.lower() for word in ('login','register','signin','oauth','sso')):
                result['status']='skipped_login'
        elif response.status_code==200:
            soup=BeautifulSoup(response.content,'html.parser')
            result.update(status='page_reachable_only',page_title=soup.title.get_text(' ',strip=True) if soup.title else '',sha256=hashlib.sha256(response.content).hexdigest())
            result['catalog_links']=[urljoin(url,a['href']) for a in soup.select('a[href]') if any(word in a.get_text() for word in ('数据目录','开放目录','数据集'))][:20]
            result['script_urls']=[urljoin(url,s['src']) for s in soup.select('script[src]')][-10:]
            for meta in soup.select('meta[http-equiv]'):
                if meta['http-equiv'].lower()!='refresh': continue
                match=re.search(r';\s*url\s*=\s*(.+)$',meta.get('content',''),re.I)
                if not match: continue
                target=urljoin(url,match[1].strip().strip('\'"'))
                if urlparse(target).scheme not in ('http','https'): continue
                result.update(status='redirect_unverified',redirect=target,redirect_method='html-meta-refresh')
                if any(word in urlparse(target).path.lower() for word in ('login','register','signin','oauth','sso')):
                    result['status']='skipped_login'
                break
        else:
            result['status']='deferred_http'
    except httpx.HTTPError as exc:
        result.update(status='deferred_network',error=type(exc).__name__+': '+str(exc)[:200],retryable=isinstance(exc,(httpx.TimeoutException,httpx.ConnectError)) and 'CERTIFICATE' not in str(exc))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',default='docs/local-platform-candidates.json')
    parser.add_argument('--output',default='artifacts/national-platform-audit.jsonl')
    parser.add_argument('--level',choices=['省级','副省级','地市级'])
    parser.add_argument('--retries',type=int,choices=range(4),default=0)
    args=parser.parse_args()
    items=json.loads(Path(args.input).read_text(encoding='utf-8'))
    pending=list({x['url']:x for x in items if (not args.level or x['level']==args.level) and urlparse(x['url']).scheme in ('http','https')}.values())
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('a',encoding='utf-8') as stream:
        # First visit every candidate; only then retry temporary failures.
        for attempt in range(1,args.retries+2):
            retry=[]
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures=[pool.submit(probe,item,attempt) for item in pending]
                for future in as_completed(futures):
                    result=future.result()
                    stream.write(json.dumps(result,ensure_ascii=False)+'\n');stream.flush()
                    print(result['name'],result['status'],result.get('http_status',''),flush=True)
                    if result['retryable']:retry.append({k:v for k,v in result.items() if k in ('name','area','level','url','discovered_from','reference_year')})
            pending=retry
            if not pending:break


if __name__=='__main__':main()
