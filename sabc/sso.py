"""Browser-bound, single-use ticket SSO with live main-site revocation checks."""
import hashlib
import hmac
import math
import os
import re
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from sabc.sso_sessions import SessionStore

router = APIRouter(prefix='/api/sso')
COOKIE = 'sabc_sso_session'
STATE_COOKIE = 'sabc_sso_state'


def enabled():
    return os.getenv('SABC_AUTH_MODE') == 'sso'


def main_origin():
    return os.environ['SABC_SSO_MAIN_ORIGIN'].rstrip('/')


def identity(request):
    key = hashlib.sha256(request.cookies.get(COOKIE, '').encode()).hexdigest()
    sessions = SessionStore()
    entry = sessions.get(key)
    if not entry or entry['expires'] <= time.time():
        sessions.delete(key)
        return None
    if time.time() - entry['checked'] >= 15:
        try:
            response = httpx.get(main_origin() + '/api/sso/session',
                                headers={'Authorization': 'Bearer ' + entry['token']}, timeout=10)
            if response.status_code in (401, 403, 404):
                sessions.delete(key)
                return None
            response.raise_for_status()
            user = response.json()['data']['user']
            if user['id'] != entry['user']['id']:
                sessions.delete(key)
                return None
            entry.update(user=user, checked=time.time())
            if not sessions.refresh(key, entry):
                return None
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise HTTPException(503, '主站登录校验暂时不可用，请稍后重试')
    return entry['user']


@router.get('/start')
def start():
    if not enabled():
        raise HTTPException(404)
    state = secrets.token_urlsafe(32)
    response = RedirectResponse(main_origin() + '/home2?' + urlencode({'externalSso': 'sabcxm', 'state': state}), status_code=302)
    response.set_cookie(STATE_COOKIE, state, max_age=300, httponly=True, secure=True, samesite='lax', path='/api/sso')
    response.headers['Cache-Control'] = 'no-store'
    return response


@router.get('/callback')
def callback(request: Request, ticket: str = '', state: str = ''):
    if not enabled():
        raise HTTPException(404)
    expected = request.cookies.get(STATE_COOKIE, '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', state) or not expected or not hmac.compare_digest(expected, state):
        raise HTTPException(400, '登录请求已过期，请从主站重新进入')
    if not ticket or len(ticket) > 256:
        raise HTTPException(400, '无效的登录票据')
    try:
        result = httpx.post(main_origin() + '/api/external-sso/sabcxm/exchange',
                            headers={'x-qycm-sso-client-secret': os.environ['SABC_SSO_CLIENT_SECRET']},
                            json={'ticket': ticket}, timeout=15)
        result.raise_for_status()
        data = result.json()['data']
        user = data['user']
        if not isinstance(user['id'], str) or not user['id'] or not isinstance(data['token'], str):
            raise ValueError('Invalid identity')
        # Check current account permissions before creating a local session.
        checked = httpx.get(main_origin() + '/api/sso/session', headers={'Authorization': 'Bearer ' + data['token']}, timeout=10)
        checked.raise_for_status()
        if checked.json()['data']['user']['id'] != user['id']:
            raise ValueError('Identity mismatch')
        expires = float(data['expiresAt']) / 1000
        if not math.isfinite(expires) or expires <= time.time():
            raise ValueError('Expired ticket')
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(401, '主站登录未完成，请重新登录主站后进入')
    token = secrets.token_urlsafe(32)
    SessionStore().save(hashlib.sha256(token.encode()).hexdigest(), {'user': user, 'token': data['token'], 'expires': expires, 'checked': time.time()})
    response = RedirectResponse('/', status_code=303)
    response.set_cookie(COOKIE, token, max_age=int(expires - time.time()), httponly=True, secure=True, samesite='lax', path='/api')
    response.delete_cookie(STATE_COOKIE, path='/api/sso', secure=True, httponly=True, samesite='lax')
    response.headers.update({'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
    return response


def logout(request, response):
    key = hashlib.sha256(request.cookies.get(COOKIE, '').encode()).hexdigest()
    if enabled():
        SessionStore().delete(key)
    response.delete_cookie(COOKIE, path='/api')
