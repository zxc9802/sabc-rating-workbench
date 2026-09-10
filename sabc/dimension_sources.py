"""Dimension allowlists constrain answer-model retrieval tasks."""
import os
import re
from datetime import datetime, timezone
from sabc.sources import request_spec

SOURCES = {
    'strategy': ['web', 'miit'],
    'market': ['web', 'local', 'stats', 'worldbank', 'apple', 'trends'],
    'return': ['web', 'cninfo', 'sec'],
    'resources': ['web', 'github'],
    'replication': ['web', 'github'],
    'cash': ['web'],
    'risk': ['law', 'web', 'miit'],
    'opportunity': ['web'],
}
PROMPT = '''
外部核查采用八维规则，不使用向量决定是否查询。data_requests的每项必须含dimension（八维英文键）、source、query、reason。
按具体外部事实缺口提出任务，不因提到某维就查询；内部预算、人员、目标无需查询。候选接口：%s。
市场规模、竞品、海外准入、合规适用等重要外部假设应主动提出核查任务，不必等用户说“搜索”。query是精炼独立的公开检索词，包含已知目标国家/地区、产品、核查主题，必要时带年份；不能复制用户整段回复，不能发送内部资金、客户信息或密钥。不明确的参数先问，不猜。
中国法律库仅用于明确中国适用的事项；海外法规使用web搜索目标国官方部门，不能用中国法替代。百度指数/抖音指数/专利/工商目前不支持自动调用，不声称已查。
每轮至多2项。已有同主题证据先复用。查询结果未返回前，reply只说明正在核查的业务问题，不得提前给出依赖结果的结论。结果返回后说明支持或未能支持什么；失败与无结果保留为未核查，不能当作负面事实或成功证据。
''' % SOURCES


def plan_requests(requests, evidence, latest):
    selected, outcomes, seen = [], [], set()
    for r in requests[:2]:
        source, query, dim = r.get('source'), r.get('query', '').strip(), r.get('dimension')
        status = None
        if source not in SOURCES.get(dim, []):
            status = 'dimension_not_allowed'
        elif source == 'web' and not os.getenv('ANYSEARCH_API_KEY'):
            status = 'unavailable'
        elif source == 'web' and (len(query)>160 or re.search(r'sk-|密钥|身份证|手机号|客户名单|\b\d{7,}\b|@', query, re.I)):
            status = 'unsafe_query'
        else:
            try:
                request_spec(source, query)
            except (ValueError, KeyError, TypeError):
                status = 'invalid_parameters'
        key = (source, query)
        if not status and key in seen:
            status = 'duplicate'
        seen.add(key)
        today = datetime.now(timezone.utc).date().isoformat()
        if not status and not re.search('重新查|刷新|最新', latest) and any(e.get('source_id')==source and e.get('query')==query and str(e.get('retrieved_at',''))[:10]==today for e in evidence):
            status = 'existing_evidence'
        outcomes.append({**r, 'status':status or 'selected'})
        if not status:
            selected.append({**r, 'query':query})
    return {'method':'dimension_rules', 'data_requests':selected, 'candidates':outcomes}
