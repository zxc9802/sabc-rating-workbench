"""Local records and append-only, hash-linked change history."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS records(kind TEXT,id TEXT,payload TEXT,created_at TEXT,PRIMARY KEY(kind,id))')
            db.execute('CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY, payload TEXT,previous_hash TEXT,hash TEXT)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=20)

    def get(self,kind,ident):
        with self.connect() as db:
            row=db.execute('SELECT payload FROM records WHERE kind=? AND id=?',(kind,ident)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self,kind):
        with self.connect() as db:
            rows=db.execute('SELECT payload FROM records WHERE kind=? ORDER BY created_at DESC',(kind,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def save(self,kind,record):
        record={**record,'id':record.get('id') or uuid4().hex,'updated_at':utcnow()}
        record.setdefault('created_at',record['updated_at'])
        payload=json.dumps(record,ensure_ascii=False,sort_keys=True)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT 1 FROM records WHERE kind=? AND id=?',(kind,record['id'])).fetchone()
            if existing and kind in ('assessments','companies','evidence'):
                raise ValueError('历史版本不能被覆盖，请创建新版本')
            db.execute('INSERT OR REPLACE INTO records VALUES(?,?,?,?)',(kind,record['id'],payload,record['created_at']))
            previous=db.execute('SELECT hash FROM audit ORDER BY seq DESC LIMIT 1').fetchone()
            previous=previous[0] if previous else ''
            entry=json.dumps({'kind':kind,'record':record},ensure_ascii=False,sort_keys=True)
            digest=hashlib.sha256((previous+entry).encode()).hexdigest()
            db.execute('INSERT INTO audit(payload,previous_hash,hash) VALUES(?,?,?)',(entry,previous,digest))
        return record

    def check_audit(self):
        previous=''
        with self.connect() as db:
            rows=db.execute('SELECT payload,previous_hash,hash FROM audit ORDER BY seq').fetchall()
        for payload,prev,digest in rows:
            if prev!=previous or hashlib.sha256((previous+payload).encode()).hexdigest()!=digest: return False
            previous=digest
        return True
