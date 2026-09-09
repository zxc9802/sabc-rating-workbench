"""Authenticated TLS transport; a transport failure never falls back to local data."""
import base64
import os
import ssl
from urllib.parse import urlparse

import httpx

from sabc.store import utcnow


def collect_remote(store,project_id,source,query):
    base=os.environ['SABC_COLLECTOR_URL'].rstrip('/')
    if urlparse(base).scheme!='https': raise ValueError('上海采集服务必须使用HTTPS')
    token=os.getenv('SABC_COLLECTOR_TOKEN','')
    if len(token)<32: raise ValueError('上海采集服务鉴权尚未配置')
    try:
        context=ssl.create_default_context()
        certificate=os.getenv('SABC_COLLECTOR_CA_B64','')
        if certificate: context.load_verify_locations(cadata=base64.b64decode(certificate,validate=True).decode())
        with httpx.Client(verify=context,timeout=httpx.Timeout(195,connect=10),follow_redirects=False,trust_env=False) as client:
            response=client.post(base+'/v1/collect',headers={'Authorization':'Bearer '+token},json={'source':source,'query':query})
        if response.status_code not in (200,422):
            raise ValueError(f'上海采集连接失败（HTTP {response.status_code}），未返回证据')
        result=response.json()
        if result.get('collector_region')!='ap-shanghai' or not result.get('job_id'):
            raise ValueError('上海采集返回格式无效，未保存证据')
        evidence=result.get('evidence',{})
        if result.get('status')=='success':
            required=('title','source_locator','content','data_period','scope','retrieved_at','payload_sha256')
            if evidence.get('source_id')!=source or evidence.get('query')!=query or any(not isinstance(evidence.get(k),str) or not evidence[k] for k in required):
                raise ValueError('上海采集证据与请求不一致，未保存')
            evidence={k:v for k,v in evidence.items() if k not in ('id','project_id','created_at','updated_at')}
            evidence=store.save('evidence',{**evidence,'project_id':project_id,'level':0,'verification_status':'unverified','source_type':'market','collector_region':'ap-shanghai','collector_job_id':result['job_id']})
        for run in result.get('runs',[]):
            data={k:v for k,v in run.items() if k not in ('id','project_id','created_at','updated_at','evidence_id')}
            store.save('source_runs',{**data,'project_id':project_id,'source':source,'query':query,'collector_region':'ap-shanghai','collector_job_id':result['job_id'],**({'evidence_id':evidence['id']} if result.get('status')=='success' and run.get('status')=='success' else {})})
        if result.get('status')!='success': raise ValueError(str(result.get('error','上海采集失败，未返回证据'))[:500])
        return evidence
    except (httpx.HTTPError,ValueError,KeyError,TypeError) as error:
        detail=str(error) if isinstance(error,ValueError) else '上海采集连接异常，未取得可用结果'
        store.save('source_runs',{'project_id':project_id,'source':source,'query':query,'status':'failed','collector_region':'ap-shanghai','round':utcnow(),'attempt':0,'error':detail,'next_step':'远程请求不自动重试；检查上海服务后再发起查询'})
        raise ValueError(detail) from None
