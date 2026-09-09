"""Import an explicitly captured official browser observation without cookies."""
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sabc.app import Evidence
from sabc.store import Store, utcnow


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('capture',type=Path)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--project',required=True)
    args=parser.parse_args()
    capture=json.loads(args.capture.read_text(encoding='utf-8-sig'))
    source=capture['source_id']
    hosts={'trends':{'trends.google.com'},'baidu':{'index.baidu.com'},'douyin':{'trendinsight.oceanengine.com','creator.douyin.com'},'gsxt':{'www.gsxt.gov.cn'},'patent':{'ipdps.cnipa.gov.cn'}}
    url=urlparse(capture['source_locator'])
    if url.scheme!='https' or url.hostname not in hosts.get(source,set()): raise ValueError('来源与官方域名不匹配')
    evidence=Evidence.model_validate(capture).model_dump()
    if not evidence['data_period'] or not evidence['scope'] or not evidence['content']: raise ValueError('必须记录期间、范围和实际观察内容')
    store=Store(args.database)
    if not store.get('projects',args.project): raise ValueError('项目不存在')
    evidence.update(project_id=args.project,source_id=source,source_type='market',verification_status='unverified',level=0,retrieved_at=capture.get('retrieved_at') or utcnow(),capture_method='browser-observation')
    record=store.save('evidence',evidence)
    store.save('source_runs',{'source':source,'project_id':args.project,'status':'success','method':'browser-observation','evidence_id':record['id'],'attempt':1,'query':capture.get('query','')})
    print(record['id'])


if __name__=='__main__': main()
