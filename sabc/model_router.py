"""Request-local model retries and ordered fallbacks."""
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
    primary = {**preferred, 'primary': True, 'deepseek': False}
    model = preferred.get('model', '').lower().replace('-', '').replace('.', '')
    if model.startswith('glm53'):
        # Retry GLM once, then use Luna on exactly the same endpoint and credentials.
        routes = [{**primary, 'single_attempt': True, 'attempt': attempt} for attempt in (1, 2)]
        routes.append({**preferred, 'model': 'gpt-5.6-luna', 'primary': False, 'deepseek': False})
    else:
        routes = [primary]
    if fallback:
        routes.append(fallback)
    for index, config in enumerate(routes):
        check_cancelled()
        started = time.monotonic()
        event = {'role': role, 'model': config['model'], 'primary': config['primary'], 'attempt': config.get('attempt', 1)}
        try:
            result = execute(config)
            check_cancelled()
        except Exception as error:
            event.update(status='failed', error_type=type(error).__name__)
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
