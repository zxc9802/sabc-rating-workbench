"""Regional public previews and explicitly captured browser observations."""
import hashlib
import html
import json
import re
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup

from sabc.store import utcnow

REGIONS = [
    dict(id='suqian',name='宿迁（江苏）',url='https://data.suqian.gov.cn/sjkfpt.shtml',method='公开统计文章搜索',note='当前列表首篇匹配文章，非全量历史检索；累计口径见原文',example='suqian/search:商务统计'),
    dict(id='aksu',name='阿克苏（新疆）',url='https://www.aks.gov.cn/sjkf/index.html',method='公开统计图表接口',note='地区生产总值及三次产业；季度可能为累计值，不代表全疆',example='aksu/gdp:2025'),
    dict(id='hangzhou',name='杭州',url='https://data.hangzhou.gov.cn/',method='浏览器预览',note='已取富阳市场8行；完整下载需确认许可协议'),
    dict(id='shanghai',name='上海',url='https://data.sh.gov.cn/',method='暂缓',note='程序返回412，浏览器空白；尚未取得数据'),
    dict(id='guangzhou',name='广州',url='https://gddata.gd.gov.cn/index',method='浏览器预览',note='通过开放广东；已取养老机构预览10行，非全量'),
    dict(id='shenzhen',name='深圳',url='https://opendata.sz.gov.cn/',method='自动预览',note='无条件开放库表；样例最多50行，不是全量API',example='shenzhen/29200_00403632'),
    dict(id='shandong',name='山东',url='https://data.sd.gov.cn/portal/index',method='自动搜索与预览',note='匿名搜索官方目录并读取公开记录；非全量',example='shandong/search:社会消费品零售总额'),
    dict(id='dazhou',name='达州',url='https://www.dazhoudata.cn/oportal/index',method='自动搜索与预览',note='匿名搜索官方目录并读取公开记录',example='dazhou/search:人口'),
    dict(id='panzhihua',name='攀枝花',url='https://pzhdata.cn/oportal/index',method='自动搜索与预览',note='匿名搜索官方目录并读取公开记录',example='panzhihua/search:常住人口'),
    dict(id='yaan',name='雅安',url='https://www.yasdata.cn/oportal/index',method='自动搜索与预览',note='已验证区县人口公开记录；非全量',example='yaan/search:人口'),
    dict(id='yibin',name='宜宾',url='http://data.yibin.cn/oportal/index',method='自动搜索与预览',note='官方HTTP入口；已验证人口普查公开记录，非全量',example='yibin/search:人口'),
    dict(id='suzhou_ah',name='宿州（安徽）',url='https://www.ahsz.gov.cn/opendata/index',method='自动搜索与预览',note='仅无条件开放目录；已验证2023年人口教育统计',example='suzhou_ah/search:人口'),
    dict(id='fujian',name='福建',url='https://data.fujian.gov.cn/',method='自动搜索与预览',note='仅普遍开放目录；公开预览最多30行，须核对省级或地市范围',example='fujian/search:森林公园'),
]
HOSTS = {'suqian':'www.suqian.gov.cn','aksu':'www.aks.gov.cn','hangzhou':'data.hangzhou.gov.cn','shanghai':'data.sh.gov.cn','guangzhou':'gddata.gd.gov.cn','shenzhen':'opendata.sz.gov.cn','shandong':'data.sd.gov.cn'}
PORTALS = {'shandong':'https://data.sd.gov.cn/portal','dazhou':'https://www.dazhoudata.cn/oportal','panzhihua':'https://pzhdata.cn/oportal'}
PORTALS.update({'yaan':'https://www.yasdata.cn/oportal','yibin':'http://data.yibin.cn/oportal'})
PORTALS['suzhou_ah']='https://www.ahsz.gov.cn/oportal'
SHANDONG_CITIES = [
    ('zaozhuang', '枣庄', 'http://zzdata.sd.gov.cn/zaozhuang', 'zaozhuang/search:人口'),
    ('zibo', '淄博', 'http://zbdata.sd.gov.cn/zibo', 'zibo/search:人口'),
    ('dongying', '东营', 'http://dydata.sd.gov.cn/dongying', 'dongying/search:生产总值'),
    ('yantai', '烟台', 'http://ytdata.sd.gov.cn/yantai', 'yantai/search:人口'),
    ('weifang', '潍坊', 'http://wfdata.sd.gov.cn/weifang', 'weifang/search:人口'),
    ('taian', '泰安', 'http://tadata.sd.gov.cn/taian', 'taian/search:人口'),
    ('rizhao', '日照', 'http://rzdata.sd.gov.cn/rizhao', 'rizhao/search:人口'),
    ('linyi', '临沂', 'http://lydata.sd.gov.cn/linyi', 'linyi/search:人口'),
    ('dezhou', '德州', 'http://dzdata.sd.gov.cn/dezhou', 'dezhou/search:人口'),
    ('liaocheng', '聊城', 'http://lcdata.sd.gov.cn/liaocheng', 'liaocheng/search:人口'),
    ('binzhou', '滨州', 'http://bzdata.sd.gov.cn/binzhou', 'binzhou/search:人口'),
    ('heze', '菏泽', 'http://hzdata.sd.gov.cn/heze', 'heze/search:人口'),
]
for region,name,base,example in SHANDONG_CITIES:
    PORTALS[region]=base
    REGIONS.append(dict(id=region,name=name,url=base+'/index',method='自动搜索与预览',note='已验证公开统计记录；可能为区县数据，非全市全量',example=example))
HOSTS.update({region:urlparse(base).netloc for region,base in PORTALS.items()})
HOSTS['fujian']='data.fujian.gov.cn'
FUJIAN_API='https://data.fujian.gov.cn/datadevelop/prod-api/open-portal'
FUJIAN_CITIES={
    'fuzhou_fj':('福州','350100000000','生产总值'),
    'xiamen':('厦门','350200000000','生产总值'),
    'zhangzhou':('漳州','350600000000','生产总值'),
    'quanzhou':('泉州','350500000000','生产总值'),
    'sanming':('三明','350400000000','生产总值'),
    'putian':('莆田','350300000000','生产总值'),
    'nanping':('南平','350700000000','生产总值'),
    'longyan':('龙岩','350800000000','旅行社'),
    'ningde':('宁德','350900000000','生产总值'),
    'pingtan':('平潭综合实验区','350128000000','生产总值'),
}
for region,(name,code,keyword) in FUJIAN_CITIES.items():
    HOSTS[region]='data.fujian.gov.cn'
    REGIONS.append(dict(id=region,name=name,url='https://data.fujian.gov.cn/',method='按地市自动搜索与预览',note='通过福建省平台按地区筛选；可能包含辖区县数据，最多30行',example=region+'/search:'+keyword))


def fujian_get(client, path, params):
    response=public_request(client,'get',FUJIAN_API+path,params=params)
    payload=response.json()
    if str(payload.get('code'))!='200':
        raise ValueError('福建接口未返回可用数据，已跳过：'+str(payload.get('msg',''))[:100])
    return response,payload.get('data')


def public_request(client, method, url, **kwargs):
    response=getattr(client,method)(url,follow_redirects=False,**kwargs)
    if response.is_redirect:
        raise ValueError('平台要求跳转，已跳过；不自动进入登录或注册流程')
    response.raise_for_status()
    return response


def validate_public_fields(columns):
    names=' '.join(f.get('name') or '' for f in columns)
    if any(k in names for k in ('身份证','人脸','指纹','银行卡')) or ('姓名' in names and any(k in names for k in ('手机号','出生日期','民族'))):
        raise ValueError('目录为个人明细，不适合作为项目市场统计依据；已跳过')


def search_local(client, region, keyword):
    if region not in {*PORTALS,*FUJIAN_CITIES,'fujian'} or not keyword.strip() or len(keyword)>60:
        raise ValueError('请选择支持搜索的地区并提供1至60字关键词')
    if region=='fujian' or region in FUJIAN_CITIES:
        params={'pageNum':1,'pageSize':10,'key':keyword,'openType':'1'}
        if region in FUJIAN_CITIES:
            params.update(cityCode=FUJIAN_CITIES[region][1],currentTab='city',type=2)
        _,data=fujian_get(client,'/catalog/list',params)
        results=[]
        for row in (data or {}).get('rows',[]):
            ident=row.get('catalogID','');title=row.get('catalogName','')
            if row.get('openType')!='1' or not all(t in title for t in keyword.split()): continue
            try: parse_query('fujian/'+ident)
            except ValueError: continue
            results.append({'title':title,'query':'fujian/'+ident,'url':FUJIAN_API+'/catalog/getCataInfo?cataId='+ident})
        return results[:10]
    base=PORTALS[region]
    response=public_request(client,'get',base+'/catalog/index',params={'Q':keyword,'openType':'1'})
    soup=BeautifulSoup(response.content.decode('utf-8'),'html.parser')
    results=[]; seen=set()
    for link in soup.select('a[href]'):
        locator=urljoin(base+'/',link['href'])
        if not locator.startswith(base+'/catalog/'): continue
        ident=locator.removeprefix(base+'/catalog/')
        if not re.fullmatch(r'(?:\d{20}|[a-f0-9]{32})',ident) or ident in seen: continue
        title=link.get_text(' ',strip=True)
        if not all(term in title for term in keyword.split()): continue
        card=link.find_parent('li') or link.parent
        status=card.get_text(' ',strip=True)
        if '无条件' not in status or '有条件' in status: continue
        seen.add(ident)
        results.append({'title':title,'query':region+'/'+ident,'url':locator})
    return results[:20]


def parse_query(query):
    region,sep,ident=query.partition('/')
    if region=='suqian' and sep and ident.startswith('search:') and 0<len(ident[7:].strip())<=60:
        return region,ident
    if region=='aksu' and sep and re.fullmatch(r'gdp:20[0-9]{2}',ident):
        return region,ident
    if sep and region in {*PORTALS,*FUJIAN_CITIES,'fujian'} and ident.startswith('search:') and 0<len(ident[7:].strip())<=60:
        return region,ident
    pattern=r'(?:\d{20}|[a-f0-9]{32})' if region in PORTALS else {'shenzhen':r'\d{5}_\d{8}','fujian':r'(?:[A-Fa-f0-9]{32}|\d{12}/\d{1,12})'}.get(region)
    if not sep or not pattern or not re.fullmatch(pattern,ident):
        raise ValueError('自动查询格式：shenzhen/29200_00403632、shandong/目录编号，或 dazhou/search:人口；仅支持已验证地区')
    return region,ident


def fetch_local(client, query):
    region,ident=parse_query(query)
    if region=='suqian':
        from sabc.suqian_source import fetch_article
        return fetch_article(client,ident[7:].strip())
    if region=='aksu':
        from sabc.aksu_source import fetch_gdp
        return fetch_gdp(client,ident[4:])
    if ident.startswith('search:'):
        keyword=ident[7:].strip()
        candidates=search_local(client,region,keyword)
        if not candidates: raise ValueError('未找到匹配的无条件开放目录，未生成数据证据')
        skipped=[]
        for candidate in candidates[:3]:
            try:
                result=fetch_local(client,candidate['query'])
            except ValueError as exc:
                skipped.append({'query':candidate['query'],'reason':str(exc)[:160]})
                continue
            result['facts']['selection']={'keyword':keyword,'selected':candidate,'candidate_count':len(candidates),'skipped':skipped,'method':'官方目录首个可读取匹配结果，需核验业务适用性'}
            if region in FUJIAN_CITIES:
                result['facts']['region']=region
                result['facts']['selection']['city_filter']={'name':FUJIAN_CITIES[region][0],'code':FUJIAN_CITIES[region][1]}
            return result
        raise ValueError('匹配目录未取得可用市场数据：'+ '; '.join(x['reason'] for x in skipped))
    base='https://'+HOSTS[region]
    if region=='fujian':
        params={'cataId':ident}
        page,meta=fujian_get(client,'/catalog/getCataInfo',params)
        if not isinstance(meta,dict) or meta.get('openType')!='1':
            raise ValueError('福建仅自动读取普遍开放目录；依申请开放已跳过')
        _,items=fujian_get(client,'/catalog/getCataItem',params)
        columns=[{'key':f.get('nameEn'),'name':f.get('nameCn','')} for f in items or []]
        validate_public_fields(columns)
        response,data=fujian_get(client,'/catalog/getCataItemData',{**params,'searchKey':'','searchKeyColumnId':''})
        rows=(data or {}).get('rows')
        if not isinstance(rows,list) or not rows: raise ValueError('福建目录未取得实际预览记录')
        rows=rows[:30];total=meta.get('dataVol')
        metadata={k:meta.get(k) for k in ('catalogID','catalogName','catalogDes','orgName','themeName','dataUpdateTime','updateCycle')}
        title=meta.get('catalogName');locator=str(page.url)
        period='具体统计期间见原始记录；目录更新时间 '+str(meta.get('dataUpdateTime','待核验'))+' 不等于数据期间'
        limitation='福建平台公开预览最多30行；来源可能为地市或区县，不保证全省覆盖。面积等指标须核对单位，不能由名录数量推算需求或收入。'
    elif region=='shenzhen':
        res_id=ident.replace('_','/')
        response=public_request(client,'post',base+'/data/catalog/selectDataCatalogByResId',data={'resId':res_id})
        response.raise_for_status(); meta=response.json()
        if meta.get('openLevelName')!='无条件开放': raise ValueError('只自动读取无条件开放数据；其他数据需登录申请')
        if not meta.get('sourceTableName'): raise ValueError('该目录仅提供文件，请在官方平台下载后导入')
        fields=public_request(client,'post',base+'/data/dataSet/getPreviewDataItem',data={'resId':res_id})
        fields.raise_for_status()
        response=public_request(client,'get',base+'/data/dataSet/getPreviewData',params={'resId':res_id,'tableName':meta['sourceTableName']})
        response.raise_for_status(); rows=response.json()
        if not isinstance(rows,list) or not rows: raise ValueError('未取得实际预览记录')
        rows=rows[:50]
        columns=[{'key':f.get('field_name'),'name':f.get('field_cn_name')} for f in fields.json()]
        metadata={k:meta.get(k) for k in ('resTitle','officeName','resAbstract','recordTotal','dataUpdateTime','updateCycle')}
        title=meta['resTitle']; total=meta.get('recordTotal')
        locator=base+'/data/dataSet/toDataDetails/'+ident
        period='平台数据更新 '+str(meta.get('dataUpdateTime','待核验'))+'；各记录日期含义见字段，非统一统计期间'
        limitation='仅公开预览前50行，不是全量数据或随机样本；名单可能重复或含跨行业经营主体，不能直接推算企业总数、客户需求或利润。'
    else:
        locator=PORTALS[region]+'/catalog/'+ident
        page=public_request(client,'get',locator)
        soup=BeautifulSoup(page.content.decode('utf-8'),'html.parser')
        entry=soup.select_one('#catalog')
        if entry is None or entry.get('opentype')!='无条件开放': raise ValueError('只自动读取无条件开放目录，未识别开放属性')
        title=entry.get('title')
        metadata={}
        for row in soup.select('table tr'):
            cells=[c.get_text(' ',strip=True) for c in row.select('td')]
            for i in range(0,len(cells)-1,2):
                if cells[i] in ('来源部门','数据时间范围','数据更新时间','地理空间范围','更新频率'):
                    metadata[cells[i]]=cells[i+1]
        response=public_request(client,'post',locator+'/getData',data={'draw':1,'start':0,'length':10,'param':''})
        response.raise_for_status(); data=response.json(); rows=data.get('data')
        if not isinstance(rows,list) or not rows: raise ValueError('未取得实际预览记录')
        rows=rows[:100]; total=data.get('recordsTotal')
        columns=[{'key':f.get('column_name_en'),'name':html.unescape(f.get('name_cn',''))} for f in data.get('items',[])]
        year_keys={'nd'} | {f['key'] for f in columns if f['name'] in ('年份','年度')}
        years=sorted({str(r[k]) for r in rows for k in year_keys if r.get(k) and re.fullmatch(r'\d{4}',str(r[k]))})
        period=(', '.join(years)+' 年度字段；' if years else '')+'具体统计期间见原始记录，目录更新时间不等于数据期间'
        limitation='仅公开预览响应，最多保留100行，不保证全量或代表性。月度累计数据若只提供年度而缺月份，不能推定月份、相加或比较增速；空值不代表零，需补齐期间和口径后使用。'
    if not title or not all(isinstance(r,dict) for r in rows): raise ValueError('数据标题或记录格式无效')
    validate_public_fields(columns)
    unique=len({json.dumps(r,ensure_ascii=False,sort_keys=True) for r in rows})
    facts={'region':region,'metadata':metadata,'fields':columns,'rows':rows,'retrieved_rows':len(rows),'distinct_rows':unique,'reported_total':total,'coverage':'公开预览；非全量保证'}
    return dict(title=title,period=period,facts=facts,limitation=limitation,locator=locator,response=response)


def save_capture(store, body):
    region=body.get('region'); locator=body.get('source_locator',''); url=urlparse(locator)
    if region not in HOSTS or url.scheme!='https' or url.netloc!=HOSTS[region]: raise ValueError('地区与官方来源域名不匹配')
    fields=('title','source_locator','data_period','scope','content','retrieved_at')
    if any(not isinstance(body.get(k),str) or not body[k].strip() for k in fields): raise ValueError('采集记录须包含标题、来源、数据期间、范围、正文和实际采集时间')
    if len(body['content'])>200000: raise ValueError('采集正文最多20万字')
    from datetime import datetime
    try:
        captured=datetime.fromisoformat(body['retrieved_at'])
        if captured.tzinfo is None: raise ValueError()
    except ValueError: raise ValueError('采集时间必须为含时区的ISO日期') from None
    record={k:body[k] for k in fields}
    record.update(region=region,source_id='local',source_type='market',level=0,verification_status='unverified',capture_method='browser-observation',canonical_source=locator,payload_sha256=hashlib.sha256(body['content'].encode()).hexdigest())
    return store.save('local_captures',record)


def use_capture(store, project_id, ident):
    capture=store.get('local_captures',ident)
    if not capture: raise ValueError('找不到该采集快照，请先导入')
    record={k:v for k,v in capture.items() if k not in ('id','created_at','updated_at')}
    record.update(project_id=project_id,capture_id=ident,source_type='market',level=0,verification_status='unverified',imported_at=utcnow())
    evidence=store.save('evidence',record)
    store.save('source_runs',dict(source='local',region=capture['region'],project_id=project_id,status='success',method='browser-observation',evidence_id=evidence['id'],attempt=1,query='capture:'+ident))
    return evidence
