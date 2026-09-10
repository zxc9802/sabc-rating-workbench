"""Persist slow operation results so short HTTP connections can safely poll them."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import time
from sabc.streaming import progress
import json
from threading import Lock
from uuid import uuid4

from fastapi import HTTPException


class Jobs:
    def __init__(self):
        self.process_id=uuid4().hex
        self.lock=Lock()
        self.pool=ThreadPoolExecutor(max_workers=2)
        self.active=set()

    def read(self,store,ident):
        job=store.get('jobs',ident)
        if job is None: raise HTTPException(404,'任务不存在')
        if job['status']=='running' and job['process_id']!=self.process_id:
            job=store.save('jobs',{**job,'status':'failed','error':'服务已重新启动，请先检查已保存记录再重试','error_status':409})
        return job

    def submit(self,store,ident,pid,request,action):
        fingerprint=hashlib.sha256(json.dumps(request,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with self.lock:
            existing=store.get('jobs',ident)
            if existing:
                if existing['fingerprint']!=fingerprint or existing['project_id']!=pid:
                    raise HTTPException(409,'任务编号已用于不同请求')
                return self.read(store,ident)
            if len(self.active)>=2: raise HTTPException(429,'正在处理其他任务，请稍后重试')
            if any(j['project_id']==pid and j['status']=='running' and j['process_id']==self.process_id for j in store.list('jobs')):
                raise HTTPException(409,'本项目已有任务正在处理，请等待结果后继续')
            job=store.save('jobs',{'id':ident,'project_id':pid,'fingerprint':fingerprint,'process_id':self.process_id,'status':'running'})
            self.active.add(ident)
            self.pool.submit(self.run,store,job,action)
            return job

    def run(self,store,job,action):
        last=[0.0, None]
        def publish(text):
            now=time.monotonic()
            if text==last[1] or (text and now-last[0]<0.2): return
            store.save('jobs',{**job,'partial_reply':text})
            last[:]=[now,text]
        token=progress.set(publish)
        try:
            result=action()
            store.save('jobs',{**job,'status':'success','result':result})
        except (ValueError,HTTPException) as error:
            store.save('jobs',{**job,'status':'failed','error':str(error) if isinstance(error,ValueError) else str(error.detail),'error_status':422 if isinstance(error,ValueError) else error.status_code})
        except Exception:
            store.save('jobs',{**job,'status':'failed','error':'任务处理失败，请检查已保存记录后重试','error_status':500})
        finally:
            progress.reset(token)
            with self.lock: self.active.discard(job['id'])


jobs=Jobs()
