"""Request-local primary retries; legacy configuration remains the fallback."""
from contextvars import ContextVar
import os
import time

from sabc.streaming import progress

audit = ContextVar('model_routing_audit', default=None)


def primary():
    key = os.getenv('SABC_DEEPSEEK_API_KEY', '').strip()
    if not key:
        return None
    return {'base_url': os.getenv('SABC_DEEPSEEK_BASE_URL', 'https://api.deepseek.com').rstrip('/'),
            'model': os.getenv('SABC_DEEPSEEK_MODEL', 'deepseek-flash'), 'key': key,
            'effort': os.getenv('SABC_DEEPSEEK_REASONING_EFFORT', 'max'), 'primary': True}


def routed(role, fallback, execute):
    route = primary()
    routes = [(route, 4)] if route else []  # Initial request plus three retries.
    routes.append(({**fallback, 'primary': False}, 1))
    for config, attempts in routes:
        for attempt in range(attempts):
            started = time.monotonic()
            event = {'role': role, 'model': config['model'], 'primary': config['primary'], 'attempt': attempt + 1}
            try:
                result = execute(config)
            except Exception as error:
                event.update(status='failed', error_type=type(error).__name__)
                if role == 'analysis' and progress.get():
                    progress.get()('')
                if not config['primary']:
                    raise
            else:
                event['status'] = 'success'
                return result
            finally:
                event['elapsed_seconds'] = round(time.monotonic() - started, 2)
                if audit.get():
                    audit.get()(event)
            if attempt + 1 < attempts:
                time.sleep(min(attempt + 1, 3))
