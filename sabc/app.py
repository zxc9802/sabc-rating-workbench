from io import BytesIO
import json
import os
from pathlib import Path
from uuid import uuid4
import zipfile

from fastapi import FastAPI, HTTPException, UploadFile, Form
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from sabc.catalog import catalog
from sabc.key_storage import encrypt_key, decrypt_key
from sabc.llm import analyze, guide
from sabc import planner
from sabc import auth
from sabc.jobs import jobs
from sabc.rating import assess, DIMENSIONS, TYPES, RULE_VERSION, PROJECT_FIELDS
from sabc.store import Store, utcnow
from sabc.schema import validate_amounts, validate_proposal
from sabc.sources import collect, SUPPORTED
from sabc.local_sources import REGIONS, save_capture, use_capture

ROOT=Path(__file__).resolve().parent.parent
store=Store(Path(os.getenv('SABC_DB',str(ROOT/'data'/'sabc.db'))))
app=FastAPI(title='SABC 项目评级',docs_url=None,redoc_url=None,openapi_url=None)
app.include_router(auth.router)


@app.middleware('http')
async def local_writes(request,call_next):
    if request.url.path not in ('/api/auth/session','/api/auth/login','/api/health') and not auth.authenticated(request):
        return JSONResponse({'detail':'请登录后继续'},status_code=401,headers={'Cache-Control':'no-store'})
    origin=request.headers.get('origin')
    if request.method not in ('GET','HEAD','OPTIONS') and origin and origin not in ('http://127.0.0.1:3000','http://localhost:3000','http://127.0.0.1:18765',os.getenv('SABC_UI_ORIGIN','http://127.0.0.1:3000')):
        return JSONResponse({'detail':'不接受其他网站的写入请求'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Cache-Control']='no-store'
    return response


@app.exception_handler(ValueError)
async def invalid(request,error):
    return JSONResponse({'detail':str(error)},status_code=422)


def project_or_404(pid):
    p=store.get('projects',pid)
    if not p: raise HTTPException(404,'项目不存在')
    return p


def company():
    records=store.list('companies')
    return records[0] if records else {}


def evidence_for(pid):
    return [e for e in store.list('evidence') if e.get('project_id')==pid]


def model_evidence_for(pid):
    return [e for e in evidence_for(pid) if not e.get('capture_id') and e.get('capture_method')!='browser-observation']


def settings():
    return store.get('settings','model') or {'base_url':os.getenv('SABC_MODEL_BASE_URL',''),'model':os.getenv('SABC_MODEL',''),'encrypted_key':''}


@app.get('/api/health')
def health():
    return {'status':'ok'}


def public_settings():
    s=settings()
    return {'base_url':s.get('base_url',''),'model':s.get('model',''),
            'has_key':bool(s.get('encrypted_key') or os.getenv('SABC_API_KEY')),
            'configured':bool(s.get('base_url') and s.get('model'))}


@app.get('/api/bootstrap')
def bootstrap():
    sources=catalog()
    runs=store.list('source_runs')
    for source in sources:
        source['status']='connected' if any(r['source']==source['id'] and r['status']=='success' for r in runs) else 'available' if source['id'] in SUPPORTED else 'browser' if source['id'] in ('baidu','douyin') else 'pending'
    return {'projects':store.list('projects'),'company':company(),'settings':public_settings(),
            'sources':sources,'rule_version':RULE_VERSION,'types':TYPES,
            'dimensions':[{'key':k,'name':n,'weight':w} for k,(n,w) in DIMENSIONS.items()]}


@app.put('/api/company')
def save_company(body:dict):
    allowed={'name','strategy','team','budget','cash_available','cash_safety_line','confirmed','capabilities','active_projects','risk_policy','approved_by'}
    data={k:v for k,v in body.items() if k in allowed}
    if 'confirmed' in data and not isinstance(data['confirmed'],bool):
        raise ValueError('公司确认状态必须为布尔值')
    validate_amounts(data, ('budget','cash_available','cash_safety_line'))
    for key in ('budget','cash_available','cash_safety_line'):
        if data.get(key) is not None and (not isinstance(data[key],(int,float)) or isinstance(data[key],bool) or data[key]<0):
            raise ValueError('预算和现金必须为非负数')
    data['version']=len(store.list('companies'))+1
    return store.save('companies',data)


@app.post('/api/projects')
def create_project(body:dict):
    validate_amounts(body, ('budget_requested',))
    data={k:v for k,v in body.items() if k in set(PROJECT_FIELDS)|{'description','budget_requested'}}
    data['name']=str(data.get('name') or '未命名项目')[:100]
    data['project_type']=data.get('project_type','growth')
    data['version']=1
    data['messages']=[]
    return store.save('projects',data)


@app.get('/api/projects/{pid}')
def get_project(pid:str):
    p=project_or_404(pid)
    return {'project':p,'evidence':evidence_for(pid),
            'assessments':[r for r in store.list('assessments') if r['project_id']==pid],
            'active_jobs':[jobs.read(store,r['id']) for r in store.list('jobs') if r['project_id']==pid and r['status']=='running']}


@app.patch('/api/projects/{pid}')
def update_project(pid:str,body:dict):
    p=project_or_404(pid)
    allowed=set(PROJECT_FIELDS)|{'description','budget_requested','proposal'}
    patch={k:v for k,v in body.items() if k in allowed}
    validate_amounts(patch, ('budget_requested',))
    if patch.get('proposal') is not None: patch['proposal']=validate_proposal(patch['proposal'])
    return store.save('projects',{**p,**patch,'pending_patch':{},'version':p['version']+1})


class Chat(BaseModel):
    message:str=Field(min_length=1,max_length=12000)
    field:str|None=None


@app.post('/api/projects/{pid}/chat')
def chat(pid:str,body:Chat):
    p=project_or_404(pid)
    messages=p.get('messages',[])+[{'role':'user','content':body.message,'time':utcnow()}]
    s=settings()
    if s.get('base_url') and s.get('model'):
        plan=None
        if planner.configured():
            try:
                plan={**planner.plan_search(p,company(),model_evidence_for(pid),messages),'status':'planned'}
            except Exception as error:
                plan={'reason':str(error),'data_requests':[],'status':'failed'}
            store.save('retrieval_plans',{'project_id':pid,'created_at':utcnow(),**plan})
            if plan['status']=='failed':
                plan={'reason':'本轮依据已有资料继续分析。','data_requests':[],'status':'skipped'}
            requests=plan['data_requests']
            result={'mode':'model','reply':'本轮外部资料尚未完成分析。','project_patch':{},'proposal':None}
        else:
            result=analyze(s,decrypt_key(s.get('encrypted_key','')),p,company(),model_evidence_for(pid),messages)
            requests=result.get('data_requests',[])
        if requests:
            outcomes=[]
            for request in requests[:2]:
                try:
                    evidence=collect(store,pid,request['source'],request['query'])
                    outcomes.append({'source':request['source'],'query':request['query'],'evidence_id':evidence['id'],'status':'saved','reason':request['reason']})
                except Exception as error:
                    store.save('source_runs',{'project_id':pid,'source':request['source'],'query':request['query'],'status':'failed','error':str(error),'boundary':'chat'})
            try:
                result=analyze(s,decrypt_key(s.get('encrypted_key','')),p,company(),model_evidence_for(pid),messages+[{'role':'tool','content':'以下仅为本轮成功采集结果。未列出的渠道不使用，不描述接口错误或取数故障。依据成功结果及已有资料正常回答；资料不足只说明业务信息缺口，不虚构。仅分析现有证据，不再请求取数：'+json.dumps(outcomes,ensure_ascii=False)}])
            except ValueError:
                result={**result,'proposal':None,'reply':result['reply']+'\n资料采集已结束，但后续模型分析失败。已保存证据可在证据资料中查看，请重试分析。'}
            result['retrieval_results']=outcomes
        if plan is not None:
            if not requests:
                result=analyze(s,decrypt_key(s.get('encrypted_key','')),p,company(),model_evidence_for(pid),messages+[{'role':'tool','content':'本轮选源结果（不描述接口报错；根据已有资料正常回答）：'+json.dumps(plan,ensure_ascii=False)+'。本轮未执行采集，不得将旧证据声称为本轮新取数；仅分析现有证据，不再请求取数。'}])
            result['retrieval_plan']=plan
            result['data_requests']=[]
        # Keep earlier unconfirmed facts until the user accepts them; later explicit
        # corrections replace the same field, not the whole pending fact set.
        p['pending_patch']={**p.get('pending_patch',{}),**result.get('project_patch',{})}
    else:
        result=guide(p,body.message,body.field)
        p.update(result['project_patch'])
    followups=[q for q in result.get('questions',[])[:2] if q.strip() and q not in result['reply']]
    if followups:
        result['reply']+='\n\n'+'\n\n'.join(followups)
    valid_refs={e['id'] for e in model_evidence_for(pid)}
    refs=[eid for eid in result.get('reply_evidence_ids',[]) if eid in valid_refs]
    p['messages']=messages+[{'role':'assistant','content':result['reply'],'mode':result['mode'],'field':result.get('field'),'evidence_ids':refs,'time':utcnow()}]
    if result['mode']=='model': p['proposal']=result.get('proposal')
    if result['mode']=='model':
        readiness=assess({**p,**p.get('pending_patch',{})},company(),model_evidence_for(pid),p.get('proposal') or {})
        gaps=readiness['missing']
        state='ready' if not gaps else 'paused' if result.get('needs_external_action') else 'gathering'
        p['interview']={'state':state,'gaps':gaps,'questions':[] if state!='gathering' else result.get('questions',[]),
                        'note':'可进入人工核对，尚未批准投入' if state=='ready' else '等待补证后继续；不重复追问' if state=='paused' else '补充影响决策的关键事实'}
    p['version']+=1
    store.save('projects',p)
    return result


class Evidence(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    source_locator:str=Field(min_length=1,max_length=2000)
    content:str=Field(default='',max_length=200000)
    source_type:str='user'
    data_period:str=''
    scope:str=''
    verification_status:str='unverified'
    level:int=Field(default=0,ge=0,le=3)
    repeat_verified:bool=False
    valid_until:str|None=None
    conflict:bool=False
    canonical_source:str|None=None


class SourceQuery(BaseModel):
    query: str = Field(min_length=1,max_length=200)


@app.post('/api/projects/{pid}/sources/{source}')
def fetch_source(pid:str,source:str,body:SourceQuery):
    project_or_404(pid)
    try:
        return collect(store,pid,source,body.query)
    except Exception as error:
        store.save('source_runs',{'project_id':pid,'source':source,'query':body.query,'status':'failed','error':str(error),'boundary':'manual'})
        return {'status':'skipped'}


class SlowOperation(BaseModel):
    id:str=Field(pattern=r'^[a-f0-9-]{36}$')
    operation:str=Field(pattern=r'^(chat|source)$')
    source:str=''
    payload:dict


@app.post('/api/projects/{pid}/jobs',status_code=202)
def start_job(pid:str,body:SlowOperation):
    project_or_404(pid)
    if body.operation=='chat':
        parsed=Chat.model_validate(body.payload)
        action=lambda: chat(pid,parsed)
    else:
        parsed=SourceQuery.model_validate(body.payload)
        from sabc.sources import request_spec
        request_spec(body.source,parsed.query)
        action=lambda: fetch_source(pid,body.source,parsed)
    return jobs.submit(store,body.id,pid,body.model_dump(exclude={'id'}),action)


@app.get('/api/jobs/{ident}')
def get_job(ident:str):
    return jobs.read(store,ident)


@app.get('/api/source-runs')
def source_runs():
    return store.list('source_runs')


@app.get('/api/local-sources')
def local_sources():
    captures=store.list('local_captures')
    return {'regions':REGIONS,'captures':[{k:c[k] for k in ('id','region','title','source_locator','data_period','retrieved_at','scope')} for c in captures]}


@app.post('/api/local-captures')
def import_local_capture(body:dict):
    return save_capture(store,body)


@app.post('/api/projects/{pid}/local-captures/{ident}')
def add_local_capture(pid:str,ident:str):
    project_or_404(pid)
    return use_capture(store,pid,ident)


@app.post('/api/projects/{pid}/evidence')
def add_evidence(pid:str,body:Evidence):
    project_or_404(pid)
    return store.save('evidence',{**body.model_dump(),'project_id':pid,'retrieved_at':utcnow()})


@app.post('/api/projects/{pid}/evidence/{eid}/review')
def review_evidence(pid:str,eid:str,body:Evidence):
    project_or_404(pid)
    previous=store.get('evidence',eid)
    if not previous or previous.get('project_id')!=pid: raise HTTPException(404,'证据不存在')
    original={k:v for k,v in previous.items() if k not in ('id','created_at','updated_at')}
    reviewed={**original,**body.model_dump(),'supersedes':eid,'reviewed_at':utcnow()}
    if previous.get('source_id'):
        # Verification cannot turn an external API observation into a project experiment.
        reviewed.update(source_type='market',level=min(body.level,1),source_locator=previous['source_locator'],content=previous['content'])
    return store.save('evidence',reviewed)


def parse_file(name,content):
    suffix=Path(name).suffix.lower()
    if suffix in ('.docx','.xlsx'):
        with zipfile.ZipFile(BytesIO(content)) as z:
            if sum(i.file_size for i in z.infolist())>100_000_000: raise ValueError('文件解压后过大，请拆分后上传')
    if suffix in ('.txt','.md','.csv','.json'):
        for encoding in ('utf-8-sig','gb18030'):
            try: return content.decode(encoding)[:200000]
            except UnicodeDecodeError: pass
        raise ValueError('文件编码无法识别，请另存为UTF-8文本')
    if suffix=='.docx':
        from docx import Document
        d=Document(BytesIO(content))
        return '\n'.join([p.text for p in d.paragraphs]+[' | '.join(c.text for c in r.cells) for t in d.tables for r in t.rows])[:200000]
    if suffix=='.xlsx':
        from openpyxl import load_workbook
        w=load_workbook(BytesIO(content),read_only=True,data_only=True)
        lines=[]
        for sheet in w:
            lines.append(sheet.title)
            for row in sheet.iter_rows(max_row=5000,values_only=True): lines.append(' | '.join(str(v) if v is not None else '' for v in row))
        w.close()
        return '\n'.join(lines)[:200000]
    if suffix=='.pdf':
        from pypdf import PdfReader
        return '\n'.join(p.extract_text() or '' for p in PdfReader(BytesIO(content)).pages[:100])[:200000]
    raise ValueError('支持 TXT、MD、CSV、JSON、DOCX、XLSX 和可复制文字的PDF')


@app.post('/api/projects/{pid}/upload')
def upload(pid:str,file:UploadFile):
    project_or_404(pid)
    content=file.file.read(20_000_001)
    if len(content)>20_000_000: raise ValueError('文件超过20MB，请拆分后上传')
    try: text=parse_file(file.filename or '',content)
    except ValueError: raise
    except Exception: raise ValueError('文件无法解析，请检查文件是否损坏或受密码保护') from None
    if not text.strip(): raise ValueError('未提取到文字；扫描文件请先转成可复制的文字')
    return add_evidence(pid,Evidence(title=file.filename or '上传资料',source_locator='上传文件：'+(file.filename or '资料'),content=text))


@app.post('/api/projects/{pid}/attachments',status_code=202)
def attachment(pid:str,file:UploadFile, label:str=Form('')):
    project_or_404(pid)
    from sabc.attachments import extract, IMAGE_SUFFIXES, DOCUMENT_SUFFIXES
    name=Path(file.filename or '附件').name
    if Path(name).suffix.lower() not in IMAGE_SUFFIXES|DOCUMENT_SUFFIXES:
        raise ValueError('此格式无法读取，请上传常见文档、图片或先在浏览器抽取视频画面')
    content=file.file.read(20_000_001)
    if len(content)>20_000_000: raise ValueError('单个文档最大20MB；图片和视频请先完成本地处理')
    ident=str(uuid4())
    directory=store.path.parent/'attachments';directory.mkdir(exist_ok=True)
    path=directory/ident
    path.write_bytes(content);path.chmod(0o600)
    def process():
        result=extract(name,content,settings(),decrypt_key(settings().get('encrypted_key','')),parse_file)
        return store.save('evidence',{'project_id':pid,'title':(label or name)[:200],
            'source_locator':'对话附件：'+name,'attachment_id':ident,'source_type':'user',
            'verification_status':'unverified','level':0,'retrieved_at':utcnow(),
            'data_period':'待核对','scope':label[:500] or '本项目附件，适用范围待核对',**result})
    try:
        return jobs.submit(store,ident,pid,{'operation':'attachment','name':name},process)
    except Exception:
        path.unlink(missing_ok=True)
        raise


@app.post('/api/company/import')
def import_company(file:UploadFile):
    content=file.file.read(20_000_001)
    if len(content)>20_000_000: raise ValueError('文件超过20MB')
    try: return {'text':parse_file(file.filename or '',content),'note':'请核对并填写公司资料，导入内容不会自动成为已确认事实。'}
    except ValueError: raise
    except Exception: raise ValueError('文件无法解析') from None


@app.post('/api/projects/{pid}/assess')
def evaluate(pid:str,body:dict):
    p=project_or_404(pid)
    if any(p.get(k)!=v for k,v in p.get('pending_patch',{}).items()):
        raise ValueError('模型整理了待核对的项目事实，请先到项目资料核对并保存，再生成评级')
    proposal=body.get('proposal') or p.get('proposal') or {}
    if proposal and body.get('confirmed') is not True: raise ValueError('请先核对并确认评分建议')
    proposal=validate_proposal(proposal)
    c=company(); e=evidence_for(pid)
    result=assess(p,c,e,proposal)
    record=store.save('assessments',{'project_id':pid,'result':result,
        'snapshot':{'project':p,'company':c,'evidence':e,'proposal':proposal}})
    store.save('projects',{**p,'proposal':proposal,'last_grade':result['grade'],'last_assessment_id':record['id']})
    return record


@app.get('/api/assessments/{aid}/export')
def export(aid:str):
    record=store.get('assessments',aid)
    if not record: raise HTTPException(404,'报告不存在')
    return Response(json.dumps(record,ensure_ascii=False,indent=2),media_type='application/json',
                    headers={'Content-Disposition':f'attachment; filename="sabc-{aid[:8]}.json"'})


@app.put('/api/settings')
def save_settings(body:dict):
    from urllib.parse import urlparse
    base=str(body.get('base_url','')).strip().rstrip('/')
    if base and (urlparse(base).scheme not in ('https','http') or urlparse(base).username): raise ValueError('模型地址须为不含用户名密码的HTTP(S)地址')
    s=settings()
    data={'id':'model','base_url':base,'model':str(body.get('model','')).strip(),'encrypted_key':s.get('encrypted_key','')}
    if body.get('api_key'): data['encrypted_key']=encrypt_key(body['api_key'])
    if body.get('clear_key'): data['encrypted_key']=''
    store.save('settings',data)
    return public_settings()


@app.get('/api/health')
def health():
    return {'status':'ok','rule_version':RULE_VERSION,'audit_ok':store.check_audit()}
