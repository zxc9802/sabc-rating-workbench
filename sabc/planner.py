"""Vector capability selection with grounded, deterministic query construction."""
import os
import re
import time

from sabc import vector_sources
from sabc.model_router import audit
from sabc.local_sources import REGIONS
from sabc.sources import SUPPORTED, request_spec

COUNTRIES = {'中国':'CN', '越南':'VN', '泰国':'TH', '印尼':'ID', '印度尼西亚':'ID',
             '马来西亚':'MY', '新加坡':'SG', '菲律宾':'PH', '美国':'US', '英国':'GB',
             '日本':'JP', '韩国':'KR', '印度':'IN', '德国':'DE', '法国':'FR', '澳大利亚':'AU'}
TOPICS = ('个人信息', '数据安全', '广告', '知识产权', '劳动', '人口', '生产总值', 'GDP',
          '社会消费品零售总额', '零售额', '商务统计', '森林公园', '旅行社', '货运', '许可证')


def configured():
    # Keep the vector boundary active even when credentials are missing: do not
    # silently hand source selection back to the answer model.
    return True


def _country(text):
    found = {code for name,code in COUNTRIES.items() if name in text}
    return next(iter(found)) if len(found)==1 else None


def _query(card, text, latest):
    source = card['source']
    country_text = latest if any(name in latest for name in COUNTRIES) else text
    urls = re.findall(r'https://[^\s<>"\u3002\uff0c]+', text)
    if source in ('stats','miit','cninfo'):
        for url in urls:
            try:
                request_spec(source, url)
                return url
            except ValueError:
                pass
    elif source == 'github':
        match = re.search(r'github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)', text)
        if not match:
            match = re.search(r'(?<![\w/:.])([A-Za-z0-9_-]+/[A-Za-z0-9_.-]+)', text)
        if match:
            return match[1]
    elif source == 'sec':
        match = re.search(r'(?<![A-Za-z0-9])CIK\s*[:：=]?\s*(\d{1,10})(?!\d)', text, re.I)
        if match:
            return match[1] + ('/facts' if re.search('财务|收入|利润|现金流|财报',latest) else '')
    elif source == 'worldbank':
        match = re.search(r'(?<![A-Za-z])([A-Z]{2,3}/[A-Z][A-Z0-9.]+)', text)
        if match:
            return match[1]
        country = _country(country_text)
        if country and '人口' in text:
            return country+'/SP.POP.TOTL'
        if country and re.search(r'GDP|生产总值',text,re.I):
            return country+'/NY.GDP.MKTP.CD'
    elif source == 'local' and card.get('region'):
        region = next(r for r in REGIONS if r['id']==card['region'])
        name = region['name'].split('（')[0]
        if name not in text and region['id']+'/' not in text:
            return None
        match = re.search(re.escape(region['id'])+r'/([A-Za-z0-9_]+)(?![\w/])', text)
        if match:
            query = match[0]
            try:
                request_spec('local',query)
                return query
            except ValueError:
                pass
        if '/search:' in region.get('example',''):
            topic = next((t for t in TOPICS if t in text), None)
            if topic:
                return region['id']+'/search:'+topic
        if region['id']=='aksu' and re.search(r'GDP|生产总值',text,re.I):
            year = re.search(r'(?<!\d)20\d{2}(?!\d)',text)
            if year:
                return 'aksu/gdp:'+year[0]
    elif source == 'law':
        # Chinese-language dialogue alone does not establish jurisdiction.
        if any(name in country_text and code!='CN' for name,code in COUNTRIES.items()):
            return None
        if _country(country_text)!='CN' and not any(r['name'].split('（')[0] in text for r in REGIONS):
            return None
        match = re.search(r'\bid:([a-zA-Z0-9-]{10,80})\b',text)
        if match:
            return match[0]
        for pattern,term in [('客户|手机号|隐私|个人信息|聊天记录|脱敏','个人信息保护'),
                             ('数据安全|跨境传输','数据安全'), ('广告|宣传','广告'),
                             ('专利|知识产权|版权','知识产权'), ('劳动|雇佣|用工','劳动')]:
            if re.search(pattern,text):
                return term
    elif source == 'trends':
        # This endpoint is a trending RSS feed, not keyword history.
        if re.search('热门搜索|热搜|trending',text,re.I):
            return _country(country_text)
    elif source == 'apple':
        match = re.search(r'\b([a-zA-Z]{2})/([^\s，。；]+)',latest)
        if match and re.search('App|应用|商店|apple',text,re.I):
            return match[0]
    elif source == 'web':
        # Send only an explicitly requested public query, never company context.
        match = re.search(r'(?:搜索|检索|查一下|查询|查找|查)\s*[:：]?\s*(.+)',latest)
        if match:
            query = match[1].strip()
            if len(query)<=200 and not re.search(r'\d{7,}|@|sk-|密钥|内部|客户名单|手机号|身份证|预算|工时',query,re.I):
                return query
    return None


def plan_search(project, company, evidence, messages):
    started = time.monotonic()
    model = vector_sources.config()['model']
    event = {'role':'planner','model':model,'primary':True,'attempt':1,'method':'vector'}
    try:
        result = _plan(project, evidence, messages)
        event['status'] = 'success'
        return {**result, 'model':model, 'method':'vector', 'elapsed_seconds':round(time.monotonic()-started,2)}
    except Exception as error:
        event.update(status='failed', error_type=type(error).__name__)
        raise
    finally:
        event['elapsed_seconds'] = round(time.monotonic()-started,2)
        if audit.get():
            audit.get()(event)


def _plan(project, evidence, messages):
    latest = next((m.get('content','') for m in reversed(messages) if m.get('role')=='user'), '')
    if not latest.strip():
        return {'reason':'没有新的待核查问题。','data_requests':[], 'candidates':[]}
    context = '\n'.join(str(project.get(k,'')) for k in ('description','target_user'))[:800]
    # A short answer such as a country name needs the preceding question.
    previous = next((m.get('content','') for m in reversed(messages[:-1]) if m.get('role')=='assistant'),'')
    text = latest[:1600]+'\n项目背景：'+context
    if len(latest)<50:
        text += '\n上轮问题：'+previous[:400]
    # Rank the new request, not a long historical project description. Context is
    # retained for parameter grounding and short follow-up answers only.
    matching_text = latest[:1600]
    if len(latest)<12:
        matching_text += '\n'+previous[:300]+'\n'+context[:300]
    ranked = vector_sources.rank(matching_text)
    none_score = max(c['similarity'] for c in ranked if c['source']=='none')
    candidates = []
    requests = []
    seen = set()
    for card in ranked:
        source = card['source']
        if source not in SUPPORTED or (source=='web' and not os.getenv('ANYSEARCH_API_KEY')):
            continue
        if source=='local' and not card.get('region'):
            continue
        if card['similarity']<0.25 or card['similarity']<=none_score:
            continue
        region_text = latest if any(r['name'].split('（')[0] in latest or r['id']+'/' in latest for r in REGIONS) else text
        if source=='local' and not any(r['id']==card.get('region') and r.get('example') and (r['name'].split('（')[0] in region_text or r['id']+'/' in region_text) for r in REGIONS):
            continue
        query = _query(card,text,latest)
        item = {'id':card['id'],'similarity':round(card['similarity'],4),'status':'missing_parameters',
                'required':{'stats':'国家统计局文章完整网址','miit':'工信部文章完整网址','cninfo':'巨潮公告PDF网址','github':'明确仓库名称owner/repository','sec':'公司CIK编号','worldbank':'国家和指标','local':'目标地区及查询主题或目录标识','law':'适用国家和法规主题','trends':'热门搜索的国家；不支持关键词历史指数','apple':'商店国家/应用关键词','web':'明确的公开搜索词'}[source]}
        candidates.append(item)
        if not query:
            continue
        if source=='web' and requests:
            item['status']='covered_by_specific_source'
            continue
        try:
            request_spec(source,query)
        except ValueError:
            item['status']='invalid_parameters'
            continue
        if (source,query) in seen:
            continue
        seen.add((source,query))
        if any(e.get('source_id')==source and e.get('query')==query and str(e.get('retrieved_at',''))[:10]==time.strftime('%Y-%m-%d') for e in evidence) and not re.search('重新查|刷新|最新',latest):
            item['status']='existing_evidence'
            continue
        item['status']='selected'
        requests.append({'source':source,'query':query,'reason':'与当前待核查问题语义相关，查询参数已有依据；结果仍需核验。'})
        if len(requests)==2:
            break
    reason = '已按接口能力语义匹配，核对所需公开资料。' if requests else (
        '匹配到相关能力，但缺少明确的地区、查询词或网址等参数，或已有本日查询结果；请沿用已有资料并补问必要条件。' if candidates else '本轮没有匹配到足够相关且可用的接口，依据已有资料继续访谈；外部事实缺口仍保留。')
    if not candidates and ranked[0]['source']=='none':
        reason='本轮主要补充内部事实或整理已有资料，无需外部取数。'
    return {'reason':reason,'data_requests':requests,'candidates':candidates[:6]}
