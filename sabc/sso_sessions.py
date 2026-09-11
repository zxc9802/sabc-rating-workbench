"""Persistent SSO sessions, separate from project records and audit exports."""
import base64
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class SessionStore:
    def __init__(self):
        data = Path(os.getenv('SABC_DB', str(Path(__file__).resolve().parents[1] / 'data' / 'sabc.db')))
        self.path = data.with_name(data.stem + '-sso.db')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        secret = os.environ['SABC_SSO_MAIN_ORIGIN'].rstrip('/') + '\0' + os.environ['SABC_SSO_CLIENT_SECRET']
        self.cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, payload BLOB NOT NULL, expires REAL NOT NULL)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=20)

    def get(self, key):
        with self.connect() as db:
            row = db.execute('SELECT payload, expires FROM sessions WHERE id=?', (key,)).fetchone()
        if row is None:
            return None
        if row[1] <= time.time():
            self.delete(key)
            return None
        try:
            return json.loads(self.cipher.decrypt(row[0]))
        except (InvalidToken, ValueError):
            self.delete(key)
            return None

    def save(self, key, entry):
        payload = self.cipher.encrypt(json.dumps(entry).encode())
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE expires<=?', (time.time(),))
            db.execute('INSERT OR REPLACE INTO sessions VALUES (?, ?, ?)', (key, payload, entry['expires']))

    def refresh(self, key, entry):
        # A concurrent logout must not be undone by an in-flight main-site check.
        payload = self.cipher.encrypt(json.dumps(entry).encode())
        with self.connect() as db:
            return db.execute('UPDATE sessions SET payload=? WHERE id=? AND expires>?',
                              (payload, key, time.time())).rowcount > 0

    def delete(self, key):
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE id=?', (key,))
