"""Account-local storage selected only from the authenticated SSO identity."""
from contextvars import ContextVar
import hashlib
import os
from threading import Lock
from sabc.store import Store

account_id = ContextVar('sabc_account_id', default=None)


class AccountStore:
    def __init__(self, path):
        self.legacy = Store(path)
        self.accounts = {}
        self.lock = Lock()

    def scoped(self):
        ident = account_id.get()
        if ident is None:
            if os.getenv('SABC_AUTH_MODE') == 'sso':
                raise PermissionError('Authenticated account required')
            return self.legacy
        key = hashlib.sha256(ident.encode()).hexdigest()
        with self.lock:
            if key not in self.accounts:
                self.accounts[key] = Store(self.legacy.path.parent / 'accounts' / key / 'sabc.db')
            return self.accounts[key]

    def __getattr__(self, name):
        return getattr(self.scoped(), name)
