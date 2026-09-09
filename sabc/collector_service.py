"""Shanghai-only collection service; no model keys or business records required."""
import asyncio
import hmac
import json
import os
from pathlib import Path
import sys
import tempfile
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict

from sabc.sources import request_spec

app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
slots=asyncio.Semaphore(2)
JOB_TIMEOUT=180


@app.middleware('http')
async def authenticate(request:Request,call_next):
    token=os.getenv('SABC_COLLECTOR_TOKEN','')
    supplied=request.headers.get('authorization','')
    if len(token)<32 or not hmac.compare_digest(supplied.encode(),('Bearer '+token).encode()):
        return JSONResponse({'detail':'Unauthorized'},status_code=401)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    return response


class Collection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source:str=Field(min_length=1,max_length=20)
    query:str=Field(min_length=1,max_length=500)


@app.get('/v1/health')
def health():
    return {'status':'ok','service':'sabc-collector','region':'ap-shanghai'}


@app.post('/v1/collect')
async def collect(body:Collection):
    try: request_spec(body.source,body.query)
    except ValueError as error: raise HTTPException(422,str(error)) from None
    if slots.locked(): raise HTTPException(429,'上海采集服务繁忙，请稍后重试')
    async with slots:
        job=uuid4().hex
        with tempfile.TemporaryDirectory(prefix='sabc-collection-') as folder:
            output=Path(folder)/'result.json'
            process=await asyncio.create_subprocess_exec(sys.executable,'-m','sabc.collector_worker',job,body.source,body.query,str(output),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
            try:
                await asyncio.wait_for(process.wait(),timeout=JOB_TIMEOUT)
            except asyncio.TimeoutError:
                raise HTTPException(504,'上海采集超过180秒，任务已终止，未返回证据') from None
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
            if process.returncode!=0 or not output.exists():
                raise HTTPException(502,'上海采集任务失败，未返回有效证据')
            if output.stat().st_size>8_000_000:
                raise HTTPException(502,'采集结果过大，请缩小查询范围')
            result=json.loads(output.read_text())
            return JSONResponse({**result,'collector_region':'ap-shanghai'},status_code=200 if result['status']=='success' else 422)
