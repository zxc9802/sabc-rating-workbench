"""Persist slow operation results so short HTTP connections can safely poll them."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import hashlib
import time
from sabc.streaming import progress, cancel_signal, check_cancelled, JobCancelled
import json
from threading import Lock, Event
from uuid import uuid4

from fastapi import HTTPException


class Jobs:
    def __init__(self):
        self.process_id=uuid4().hex
        self.lock=Lock()
        self.pool=ThreadPoolExecutor(max_workers=2)
        self.active=set()
        self.signals={}
        self.futures={}

    def read(self,store,ident):
        job=store.get('jobs',ident)
        if job is None: raise HTTPException(404,'任务不存在')
        if job['status']=='running' and job['process_id']!=self.process_id:
            job=store.save('jobs',{**job,'status':'failed','error':'服务已重新启动，请先检查已保存记录再重试','error_status':409})
        return job

    def cancel_locked(self,store,ident):
        job=self.read(store,ident)
        if job['status']!='running': return job
        key=(str(store.path),ident)
        if key in self.signals: self.signals[key].set()
        if key in self.futures and self.futures[key].cancel():
            self.active.discard(key)
            self.signals.pop(key,None)
            self.futures.pop(key,None)
        return store.save('jobs',{**job,'status':'cancelled','partial_reply':'','error':'已停止回答'})

    def cancel(self,store,ident):
        with self.lock: return self.cancel_locked(store,ident)

    def submit(self,store,ident,pid,request,action,queue=False):
        if hasattr(store,'scoped'): store=store.scoped()
        key=(str(store.path),ident)
        fingerprint=hashlib.sha256(json.dumps(request,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with self.lock:
            existing=store.get('jobs',ident)
            if existing:
                if existing['fingerprint']!=fingerprint or existing['project_id']!=pid:
                    raise HTTPException(409,'任务编号已用于不同请求')
                return self.read(store,ident)
            if len(self.active)>=2 and not queue: raise HTTPException(429,'正在处理其他任务，请稍后重试')
            if any(j['project_id']==pid and j['status']=='running' and j['process_id']==self.process_id for j in store.list('jobs')):
                raise HTTPException(409,'本项目已有任务正在处理，请等待结果后继续')
            metadata={'assessment_id':request['payload']['assessment_id'],'question':request['payload']['message']} if request.get('operation')=='report_chat' else {'generate_report':True} if request.get('operation')=='chat' and request.get('payload',{}).get('generate_report') else {}
            job=store.save('jobs',{**metadata,'id':ident,'project_id':pid,'operation':request.get('operation'),'fingerprint':fingerprint,'process_id':self.process_id,'status':'running','phase':'queued'})
            self.active.add(key)
            signal=Event();self.signals[key]=signal
            self.futures[key]=self.pool.submit(copy_context().run,self.run,store,job,action,signal)
            return job

    def run(self,store,job,action,signal):
        last=[0.0, None]
        cancel_token=cancel_signal.set(signal)
        def save(update):
            with self.lock:
                check_cancelled()
                # Keep request metadata so a reloaded page can still tell this job apart.
                return store.save('jobs',{**job,**update})
        def publish(text):
            now=time.monotonic()
            if text==last[1] or (text and now-last[0]<0.2): return
            save({'partial_reply':text})
            last[:]=[now,text]
        token=progress.set(publish)
        try:
            job=save({'phase':'working'})
            result=action()
            save({'status':'success','result':result})
        except JobCancelled:
            pass
        except (ValueError,HTTPException) as error:
            with self.lock:
                if not signal.is_set(): store.save('jobs',{**job,'status':'failed','error':str(error) if isinstance(error,ValueError) else str(error.detail),'error_status':422 if isinstance(error,ValueError) else error.status_code})
        except Exception:
            with self.lock:
                if not signal.is_set(): store.save('jobs',{**job,'status':'failed','error':'任务处理失败，请检查已保存记录后重试','error_status':500})
        finally:
            progress.reset(token)
            cancel_signal.reset(cancel_token)
            with self.lock:
                self.active.discard((str(store.path),job['id']))
                self.signals.pop((str(store.path),job['id']),None)
                self.futures.pop((str(store.path),job['id']),None)


jobs=Jobs()
