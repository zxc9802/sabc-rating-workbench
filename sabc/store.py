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
        record=json.loads(row[0]) if row else None
        return None if kind=='projects' and record and record.get('deleted_at') else record

    def list(self,kind):
        with self.connect() as db:
            rows=db.execute('SELECT payload FROM records WHERE kind=? ORDER BY created_at DESC',(kind,)).fetchall()
        records=[json.loads(r[0]) for r in rows]
        return [r for r in records if not (kind=='projects' and r.get('deleted_at'))]

    def save(self,kind,record):
        record={**record,'id':record.get('id') or uuid4().hex,'updated_at':utcnow()}
        record.setdefault('created_at',record['updated_at'])
        payload=json.dumps(record,ensure_ascii=False,sort_keys=True)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            pid=record['id'] if kind=='projects' else record.get('project_id')
            if pid:
                parent=db.execute("SELECT payload FROM records WHERE kind='projects' AND id=?",(pid,)).fetchone()
                if parent and json.loads(parent[0]).get('deleted_at'):
                    raise ValueError('项目已删除')
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

    def delete_projects(self, ids):
        # Keep historical audit and evidence; remove projects from the workspace.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute("SELECT id,payload FROM records WHERE kind='projects'").fetchall()
            projects={ident:json.loads(payload) for ident,payload in rows}
            if any(ident not in projects for ident in ids):
                raise ValueError('部分项目不存在，请刷新列表后重试')
            for (payload,) in db.execute("SELECT payload FROM records WHERE kind='jobs'"):
                job=json.loads(payload)
                if job.get('project_id') in ids and job.get('status')=='running':
                    raise ValueError('所选项目仍有任务正在处理，请完成后再删除')
            for ident in ids:
                record=projects[ident]
                if record.get('deleted_at'): continue
                record={**record,'deleted_at':utcnow()}
                payload=json.dumps(record,ensure_ascii=False,sort_keys=True)
                db.execute("UPDATE records SET payload=? WHERE kind='projects' AND id=?",(payload,ident))
                previous=db.execute('SELECT hash FROM audit ORDER BY seq DESC LIMIT 1').fetchone()
                previous=previous[0] if previous else ''
                entry=json.dumps({'kind':'project_deletion','project_id':ident,'deleted_at':record['deleted_at']},sort_keys=True)
                digest=hashlib.sha256((previous+entry).encode()).hexdigest()
                db.execute('INSERT INTO audit(payload,previous_hash,hash) VALUES(?,?,?)',(entry,previous,digest))

    def check_audit(self):
        previous=''
        with self.connect() as db:
            rows=db.execute('SELECT payload,previous_hash,hash FROM audit ORDER BY seq').fetchall()
        for payload,prev,digest in rows:
            if prev!=previous or hashlib.sha256((previous+payload).encode()).hexdigest()!=digest: return False
            previous=digest
        return True
