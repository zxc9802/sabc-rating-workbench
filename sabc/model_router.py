"""Role-specific models first; DeepSeek is a request-local fallback."""
from contextvars import ContextVar
import os
import time

from sabc.streaming import progress, check_cancelled

audit = ContextVar('model_routing_audit', default=None)


def deepseek():
    key = os.getenv('SABC_DEEPSEEK_API_KEY', '').strip()
    if not key:
        return None
    return {'base_url': os.getenv('SABC_DEEPSEEK_BASE_URL', 'https://api.deepseek.com').rstrip('/'),
            'model': os.getenv('SABC_DEEPSEEK_MODEL', 'deepseek-flash'), 'key': key,
            'effort': os.getenv('SABC_DEEPSEEK_REASONING_EFFORT', 'max'), 'primary': False, 'deepseek': True}


def routed(role, preferred, execute):
    fallback = deepseek()
    routes = [{**preferred, 'primary': True, 'deepseek': False}]
    if fallback:
        routes.append(fallback)
    for index, config in enumerate(routes):
        check_cancelled()
        started = time.monotonic()
        event = {'role': role, 'model': config['model'], 'primary': config['primary'], 'attempt': 1}
        try:
            result = execute(config)
            check_cancelled()
        except Exception as error:
            event.update(status='failed', error_type=type(error).__name__)
            if role == 'analysis' and progress.get():
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
