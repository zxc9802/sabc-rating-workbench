"""Single-owner cloud login; local operation remains available without a password."""
import hashlib
import hmac
import os
import secrets
import time
from collections import deque

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router=APIRouter(prefix='/api/auth')
sessions={}
attempts=deque()
COOKIE='sabc_session'
TTL=8*60*60


def enabled():
    return bool(os.getenv('SABC_ACCESS_PASSWORD'))


def authenticated(request):
    if not enabled():
        return os.getenv('SABC_REQUIRE_AUTH')!='1'
    token=request.cookies.get(COOKIE,'')
    entry=sessions.get(hashlib.sha256(token.encode()).hexdigest())
    return bool(entry and entry[0]>time.time() and entry[1]==password_hash())


def password_hash():
    return hashlib.sha256(os.getenv('SABC_ACCESS_PASSWORD','').encode()).hexdigest()


class Login(BaseModel):
    password:str=Field(min_length=1,max_length=512)


@router.get('/session')
def session(request:Request):
    return {'authenticated':authenticated(request),'required':enabled() or os.getenv('SABC_REQUIRE_AUTH')=='1'}


@router.post('/login')
def login(body:Login):
    if not enabled():
        raise HTTPException(503,'服务器尚未配置登录密码')
    now=time.time()
    while attempts and attempts[0]<now-60: attempts.popleft()
    if len(attempts)>=30: raise HTTPException(429,'登录尝试过多，请一分钟后重试')
    attempts.append(now)
    if not hmac.compare_digest(body.password.encode(),os.environ['SABC_ACCESS_PASSWORD'].encode()):
        raise HTTPException(401,'密码不正确')
    for key,value in list(sessions.items()):
        if value[0]<=now: sessions.pop(key,None)
    if len(sessions)>=256: sessions.pop(next(iter(sessions)))
    token=secrets.token_urlsafe(32)
    sessions[hashlib.sha256(token.encode()).hexdigest()]=(now+TTL,password_hash())
    response=JSONResponse({'authenticated':True})
    response.set_cookie(COOKIE,token,max_age=TTL,httponly=True,
                        secure=os.getenv('SABC_UI_ORIGIN','').startswith('https://'),samesite='strict',path='/api')
    return response


@router.post('/logout')
def logout(request:Request):
    token=request.cookies.get(COOKIE,'')
    sessions.pop(hashlib.sha256(token.encode()).hexdigest(),None)
    response=JSONResponse({'authenticated':False})
    response.delete_cookie(COOKIE,path='/api')
    return response
