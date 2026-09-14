"""Request-local model retries and ordered fallbacks."""
from contextvars import ContextVar
import os
import time
from urllib.parse import urlparse
import httpx

from sabc.streaming import progress, check_cancelled
from sabc.model_output import ModelResponseError

audit = ContextVar('model_routing_audit', default=None)


def mixtoken_route():
    key = os.getenv('SABC_MIXTOKEN_API_KEY', '').strip()
    if not key:
        return None
    return {'base_url': os.getenv('SABC_MIXTOKEN_BASE_URL', 'https://api.mixtoken.ai/v1').rstrip('/'),
            'model': os.getenv('SABC_MIXTOKEN_MODEL', 'deepseek-v4.1-flash'), 'key': key,
            'primary': True, 'deepseek': False, 'stream': True}


def gemini_route(preferred):
    if urlparse(preferred.get('base_url', '')).hostname != 'api.openlux.ai' or not preferred.get('key'):
        return None
    return {**preferred, 'model': 'gemini-3.8-flash', 'primary': True, 'deepseek': False,
            'single_attempt': True, 'auth_scheme': 'Gemini',
            'endpoint': 'https://api.openlux.ai/v1beta/models/gemini-3.8-flash:generateContent'}


def endpoint(route):
    return route.get('endpoint') or route['base_url'].rstrip('/') + '/chat/completions'


def deepseek():
    key = os.getenv('SABC_DEEPSEEK_API_KEY', '').strip()
    if not key:
        return None
    return {'base_url': os.getenv('SABC_DEEPSEEK_BASE_URL', 'https://api.deepseek.com').rstrip('/'),
            'model': os.getenv('SABC_DEEPSEEK_MODEL', 'deepseek-flash'), 'key': key,
            'effort': os.getenv('SABC_DEEPSEEK_REASONING_EFFORT', 'max'), 'primary': False, 'deepseek': True}


def routed(role, preferred, execute):
    fallback = deepseek()
    primary = {**preferred, 'primary': True, 'deepseek': False}
    fal_key = os.getenv('SABC_FAL_API_KEY', '').strip()
    if fal_key and role in ('analysis', 'review', 'report_chat'):
        primary.update(base_url='https://fal.run/openrouter/router/openai/v1',
                       model='z-ai/glm-5.3-flash', key=fal_key, auth_scheme='Key')
    model = primary.get('model', '').split('/')[-1].lower().replace('-', '').replace('.', '')
    if model.startswith('glm53'):
        # Retry GLM once, then use Luna on the original provider endpoint and credentials.
        routes = [{**primary, 'single_attempt': True, 'attempt': attempt} for attempt in (1, 2)]
        routes.append({**preferred, 'model': 'gpt-5.6-luna', 'primary': False, 'deepseek': False})
    else:
        routes = [primary]
    if fallback:
        routes.append(fallback)
    gemini = gemini_route(preferred) if role in ('analysis', 'review', 'report_chat') else None
    if gemini:
        routes = [gemini] + [{**route, 'primary': False} for route in routes]
    mixtoken = mixtoken_route() if role in ('analysis', 'review', 'report_chat') else None
    if mixtoken:
        routes = [mixtoken] + [{**route, 'primary': False} for route in routes
                              if route.get('base_url') and route.get('model')]
    routes = [route for route in routes if route.get('base_url') and route.get('model')]
    if not routes:
        raise ValueError('模型连接尚未配置，请联系管理员')
    for index, config in enumerate(routes):
        check_cancelled()
        started = time.monotonic()
        event = {'role': role, 'model': config['model'], 'primary': config['primary'], 'attempt': config.get('attempt', 1),
                 'provider': urlparse(config.get('base_url', '')).hostname}
        try:
            result = execute(config)
            check_cancelled()
        except Exception as error:
            event.update(status='failed', error_type=type(error).__name__)
            if isinstance(error, httpx.HTTPStatusError):
                event['http_status'] = error.response.status_code
            if isinstance(error, ModelResponseError):
                event.update(error_stage=error.stage, error_details=error.details)
                if error.retry_messages and index + 1 < len(routes):
                    following = routes[index + 1]
                    if (following['model'], following.get('base_url')) == (config['model'], config.get('base_url')):
                        following['format_retry'] = error.retry_messages
            if role in ('analysis', 'report_chat') and progress.get():
                progress.get()('')
            if index == len(routes) - 1:
                raise
        else:
            event['status'] = 'success'
            return result
        finally:
            event['elapsed_seconds'] = round(time.monotonic() - started, 2)
            if audit.get():
                audit.get()(event)


def authorization(route, key):
    if route.get('auth_scheme') == 'Gemini':
        return {'x-goog-api-key': key}
    return {'Authorization': route.get('auth_scheme', 'Bearer') + ' ' + key} if key else {}
