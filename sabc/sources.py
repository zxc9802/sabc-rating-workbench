"""Free official APIs. All results remain external, indirect evidence."""
from datetime import date
from io import BytesIO
import hashlib
import json
import os
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from xml.etree import ElementTree

import httpx

from sabc.store import utcnow
from sabc.local_sources import parse_query, fetch_local

SUPPORTED = {'worldbank', 'github', 'sec', 'apple', 'stats', 'miit', 'cninfo', 'law', 'trends', 'local', 'web'}


def request_spec(source, query):
    query = query.strip()
    if source == 'web':
        if not query or len(query)>200: raise ValueError('网络搜索词须为1至200字')
        return 'https://api.anysearch.com/v1/search', {'query':query}
    if source=='local':
        parse_query(query)
        return '', {}
    if source=='trends':
        if not re.fullmatch(r'[A-Za-z]{2}',query): raise ValueError('请输入两位地区代码，例如 US；当前仅支持热门搜索 RSS')
        return 'https://trends.google.com/trending/rss', {'geo':query.upper()}
    if source=='law':
        if query.startswith('id:'):
            ident=query[3:]
            if not re.fullmatch(r'[a-zA-Z0-9-]{10,80}',ident): raise ValueError('法规编号格式无效')
            return 'https://flk.npc.gov.cn/law-search/search/flfgDetails', {'bbbs':ident}
        if not query or len(query)>100: raise ValueError('请输入100字以内的法规关键词')
        return 'https://flk.npc.gov.cn/law-search/search/list', {'searchRange':1,'sxrq':[],'gbrq':[],'searchType':2,'sxx':[],'gbrqYear':[],'flfgCodeId':[],'zdjgCodeId':[],'searchContent':query,'pageNum':1,'pageSize':5,'orderByParam':{'order':'-1','sort':''}}
    if source=='cninfo':
        parsed=urlparse(query)
        if parsed.scheme!='https' or parsed.netloc not in ('static.cninfo.com.cn','dataclouds.cninfo.com.cn') or not parsed.path.lower().endswith('.pdf'):
            raise ValueError('请输入巨潮官方公告 PDF 完整网址')
        return query, {}
    if source in ('stats','miit'):
        parsed=urlparse(query)
        hosts={'stats':{'www.stats.gov.cn'},'miit':{'www.miit.gov.cn','wap.miit.gov.cn'}}
        if parsed.scheme!='https' or parsed.netloc not in hosts[source] or not parsed.path.endswith('.html'):
            raise ValueError('请输入该部门官方 HTTPS 文章完整网址')
        return query, {}
    if source == 'github':
        if not re.fullmatch(r'[\w.-]+/[\w.-]+', query): raise ValueError('请输入 owner/repository，例如 fastapi/fastapi')
        return f'https://api.github.com/repos/{query}', {}
    if source == 'sec':
        if query.endswith('/facts'):
            cik=query.removesuffix('/facts')
            if not re.fullmatch(r'\d{1,10}',cik): raise ValueError('CIK 格式无效')
            return f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json', {}
        if not re.fullmatch(r'\d{1,10}', query): raise ValueError('请输入公司 CIK 数字，例如 320193')
        return f'https://data.sec.gov/submissions/CIK{int(query):010d}.json', {}
    if source == 'worldbank':
        parts = query.upper().split('/')
        if len(parts) != 2 or not re.fullmatch(r'[A-Z]{2,3}', parts[0]) or not re.fullmatch(r'[A-Z0-9.]+', parts[1]):
            raise ValueError('请输入国家代码/指标代码，例如 CHN/SP.POP.TOTL')
        return f'https://api.worldbank.org/v2/country/{parts[0]}/indicator/{parts[1]}', {'format':'json', 'mrv':5, 'per_page':5}
    if source == 'apple':
        parts = query.split('/', 1)
        if len(parts) != 2 or not re.fullmatch(r'[a-zA-Z]{2}', parts[0]) or not parts[1].strip():
            raise ValueError('请输入商店地区/关键词，例如 us/notion')
        return 'https://itunes.apple.com/search', {'country':parts[0].lower(), 'term':parts[1], 'entity':'software', 'limit':5}
    raise ValueError('此渠道尚未提供自动取数，请先记录官方资料')


def normalize(source, raw, query):
    today = date.today().isoformat()
    if source=='local': return raw['title'],raw['period'],raw['facts'],raw['limitation']
    if source=='trends':
        root=ElementTree.fromstring(raw)
        ns={'ht':'https://trends.google.com/trending/rss'}
        rows=[{'title':item.findtext('title'),'published_at':item.findtext('pubDate'),'approx_traffic':item.findtext('ht:approx_traffic',namespaces=ns)} for item in root.findall('./channel/item')]
        if not rows: raise ValueError('该地区没有有效热门搜索条目')
        return query.upper()+' 热门搜索', today+' 采集快照；趋势起始时间见各条 published_at', rows[:50], 'Google Trends 官方热门搜索 RSS，最多50条；不是指定关键词历史指数，不支持推断长期需求、市场规模或项目盈利。'
    if source=='law':
        if query.startswith('id:'):
            data=raw.get('data',{})
            if raw.get('code')!=200 or not data.get('title') or not raw.get('pdf_pages'): raise ValueError('未取得完整法规元数据与 PDF 条文')
            return data['title'], f"公布 {data.get('gbrq','待核验')}；生效 {data.get('sxrq','待核验')}；效力核验 {today}", {'metadata':{k:data.get(k) for k in ('bbbs','title','flxz','zdjgName','gbrq','sxrq','sxx')},'pages':raw['pdf_pages']}, '官方法规 PDF 原文；具体项目适用性仍需结合经营地区、业务事实与条款判断。'
        if raw.get('code')!=200 or not raw.get('rows'): raise ValueError('未取得有效法规检索记录')
        rows=[{**r,'title':BeautifulSoup(r['title'],'html.parser').get_text(),'detail_url':'https://flk.npc.gov.cn/detail?id='+r['bbbs']} for r in raw['rows']]
        return query+' 法规检索', today+' 效力状态快照；公布/生效日期见各条记录', {'rows':rows,'total':raw.get('total'),'status_codes':{'1':'已废止','2':'已修改','3':'有效','4':'尚未生效'}}, '标题模糊检索前5条，可能包含不相关法规；尚非条文全文，须核对适用地区与具体条款，不能直接据此判定违法或否决项目。'
    if source=='cninfo':
        from pypdf import PdfReader
        reader=PdfReader(BytesIO(raw))
        pages=[{'page':i+1,'text':p.extract_text() or ''} for i,p in enumerate(reader.pages[:100])]
        if not any(p['text'].strip() for p in pages): raise ValueError('公告未提取到文字，请使用可复制文本的 PDF')
        title=next((line.strip() for line in pages[0]['text'].splitlines() if line.strip()),'巨潮公告')
        return title[:160], '公告正文期间待核验', {'pages':pages,'total_pages':len(reader.pages),'extracted_pages':len(pages)}, '官方公告原文前100页，保留页码；超过100页的内容未采集，需核对所需财务或风险章节是否包含。'
    if source in ('stats','miit'):
        soup=BeautifulSoup(raw,'html.parser')
        body=soup.select_one('.TRS_UEDITOR, #con_con, #zoom, .article-content')
        title=soup.find('h1') or soup.title
        if body is None or title is None: raise ValueError('未识别官方文章正文，不能将首页或验证页作为证据')
        content=body.get_text('\n',strip=True)
        if len(content)<100: raise ValueError('正文过短，请检查页面是否完整')
        dates=re.findall(r'20\d{2}[年/-]\d{1,2}(?:[月/-]\d{1,2}日?)?',content[:500])
        return title.get_text(' ',strip=True), '正文期间待核对；'+', '.join(dates), {'article':content}, '官方文章原文；请核对正文统计期间、指标口径和地区，发布日期不等于数据期间。'
    if source == 'worldbank':
        rows = raw[1] if isinstance(raw,list) and len(raw)>1 else None
        rows = [r for r in rows or [] if r.get('value') is not None]
        if not rows: raise ValueError('该指标没有可用数值，请更换国家或指标')
        return rows[0]['indicator']['value'], ', '.join(r['date'] for r in rows), rows, '国家级宏观指标，不能证明本项目需求或利润。'
    if source == 'github':
        if not raw.get('full_name'): raise ValueError('未取得仓库信息')
        fields = ('full_name','description','html_url','stargazers_count','forks_count','open_issues_count','pushed_at','updated_at','archived','language','license')
        return raw['full_name'], today+' 采集时点', {k:raw.get(k) for k in fields}, '公开仓库快照；星标与提交时间不能代表付费需求或盈利。'
    if source == 'sec':
        if query.endswith('/facts'):
            facts=raw.get('facts',{}).get('us-gaap',{})
            rows=[]
            for tag in ('RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet','CostOfRevenue','CostOfGoodsAndServicesSold','GrossProfit','NetIncomeLoss','NetCashProvidedByUsedInOperatingActivities'):
                for unit,values in facts.get(tag,{}).get('units',{}).items():
                    selected=sorted((v for v in values if v.get('form') in ('10-K','10-Q')),key=lambda v:(v.get('end',''),v.get('filed','')),reverse=True)[:8]
                    rows.extend({'tag':tag,'unit':unit,**v} for v in selected)
            if not rows: raise ValueError('未取得所选 US-GAAP 财务指标')
            return raw['entityName']+' 财务指标', ', '.join(sorted({r['end'] for r in rows})), rows, '保留期间、单位、表单及申报编号；修订和季度/累计口径并列，不能直接相加或外推本项目利润。'
        recent = raw.get('filings',{}).get('recent',{})
        rows = [{k:recent[k][i] for k in ('accessionNumber','filingDate','reportDate','form','primaryDocument') if k in recent} for i in range(min(20,len(recent.get('accessionNumber',[]))))]
        if not rows: raise ValueError('该 CIK 没有近期披露记录')
        return raw['name'], ', '.join(sorted({r.get('filingDate','') for r in rows})), {'name':raw['name'],'cik':raw['cik'],'filings':rows}, '披露索引，不是财报正文或收入数据；须进一步核对相应公告。'
    rows = [{k:r.get(k) for k in ('trackId','trackName','trackViewUrl','sellerName','version','currentVersionReleaseDate','averageUserRating','userRatingCount','price','currency','primaryGenreName')} for r in raw.get('results',[])]
    if not rows: raise ValueError('该商店未找到应用，请调整关键词或地区')
    return query, today+' 商店快照', rows, '商店检索前5条；评分、价格和应用存在不能证明收入或市场规模。'


def collect(store, project_id, source, query):
    request_spec(source,query)
    if source == 'web':
        from sabc.web_search import search
        return search(store, project_id, query)
    if os.getenv('SABC_COLLECTOR_URL'):
        from sabc.remote_collector import collect_remote
        return collect_remote(store,project_id,source,query)
    return collect_local(store,project_id,source,query)


def collect_local(store, project_id, source, query):
    url, params = request_spec(source, query)
    run_id = utcnow()
    # A failed call is deferred immediately; only transient failures retry, at most three.
    for attempt in range(1,4):
        error = None
        try:
            with httpx.Client(timeout=25, follow_redirects=True, trust_env=source not in ('law','local'), headers={'User-Agent':'SABCProjectRating/0.1 research 785755358@qq.com','Accept':'application/json'}) as client:
                if source=='local':
                    raw=fetch_local(client,query); response=raw['response']
                else:
                    response = client.post(url,json=params) if source=='law' and not query.startswith('id:') else client.get(url, params=params)
                    response.raise_for_status()
                    raw = response.content if source in ('cninfo','trends') else response.content.decode('utf-8') if source in ('stats','miit') else response.json()
                if source=='law' and query.startswith('id:'):
                    download=client.get('https://flk.npc.gov.cn/law-search/download/pc',params={'format':'pdf','bbbs':query[3:],'fileId':''})
                    download.raise_for_status()
                    link=download.json().get('data',{}).get('url','')
                    if urlparse(link).scheme!='https' or urlparse(link).hostname!='flkoss.obs-bj2.cucloud.cn': raise ValueError('官方 PDF 下载地址未识别')
                    pdf=client.get(link);pdf.raise_for_status()
                    from pypdf import PdfReader
                    reader=PdfReader(BytesIO(pdf.content))
                    if len(reader.pages)>100: raise ValueError('法规超过100页，请分章节导入')
                    raw['pdf_pages']=[{'page':i+1,'text':p.extract_text() or ''} for i,p in enumerate(reader.pages)]
                    if not any(p['text'].strip() for p in raw['pdf_pages']): raise ValueError('PDF 未提取到文字')
                    raw['pdf_sha256']=hashlib.sha256(pdf.content).hexdigest()
            title, period, facts, limitation = normalize(source, raw, query)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, ElementTree.ParseError) as exc:
            error = f'HTTP {exc.response.status_code}' if isinstance(exc,httpx.HTTPStatusError) else type(exc).__name__ if isinstance(exc,httpx.HTTPError) else type(exc).__name__+': '+str(exc)[:160]
            retryable = isinstance(exc,(httpx.TimeoutException,httpx.ConnectError)) or isinstance(exc,httpx.HTTPStatusError) and exc.response.status_code in (500,502,503,504)
            store.save('source_runs',{'source':source,'project_id':project_id,'query':query,'round':run_id,'attempt':attempt,'status':'failed','error':error,'next_step':'检查网络或参数后回访；限流或验证要求先暂缓','adjustment':'首次调用' if attempt==1 else '重新建立连接，重试临时网络或服务故障'})
            if retryable and attempt<3: continue
            raise ValueError(f'{source} 取数暂缓（本轮 {attempt} 次）：{error}') from None
        content = json.dumps({'facts':facts,'limitation':limitation},ensure_ascii=False,indent=2)
        locator=raw['locator'] if source=='local' else str(response.url)
        evidence = store.save('evidence',{'project_id':project_id,'title':f'{source} · {title}','source_locator':locator,'canonical_source':locator,'query':query,'source_type':'market','content':content,'data_period':period,'scope':query+'；'+limitation,'verification_status':'unverified','level':0,'retrieved_at':utcnow(),'source_id':source,'payload_sha256':hashlib.sha256(response.content).hexdigest(),**({'region':query.split('/')[0],'capture_method':'public-preview'} if source=='local' else {})})
        store.save('source_runs',{'source':source,'project_id':project_id,'query':query,'round':run_id,'attempt':attempt,'status':'success','evidence_id':evidence['id'],'http_status':response.status_code})
        return evidence
