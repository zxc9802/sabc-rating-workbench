"""Pre-answer retrieval from dimension cues and explicit public entities."""
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
PROMPT = """
外部取数由程序在回答前按八维规则执行，你不负责选源，不得提出data_requests，该字段始终为空。
上下文含查询执行结果及缺失参数。saved仅表示已保存，不表示已核验；失败、未配置、无结果不可当成事实。missing_parameters需结合已知信息追问必要的公开产品/地区，不虚构。已有有效证据可复用。网络摘要不等于完整原文，不能据此声称法律结论已核实。不要声称将继续调用接口。
"""


def plan_requests(requests, evidence, latest):
    selected, outcomes, seen = [], [], set()
    for r in requests[:2]:
        source, query, dim = r.get('source'), r.get('query', '').strip(), r.get('dimension')
        status = None
        if source not in SOURCES.get(dim, []):
            status = 'dimension_not_allowed'
        elif source == 'web' and not os.getenv('ANYSEARCH_API_KEY'):
            status = 'unavailable'
        elif (len(query)>160 or re.search(r'sk-|密钥|身份证|手机号|客户名单|\b\d{7,}\b|@', query, re.I)):
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
        if not status and not re.search('重新查|刷新|最新', latest) and any(e.get('content') and e.get('source_id')==source and e.get('query')==query and str(e.get('retrieved_at',''))[:10]==today for e in evidence):
            status = 'existing_evidence'
        outcomes.append({**r, 'status':status or 'selected'})
        if not status:
            selected.append({**r, 'query':query})
    return {'method':'dimension_rules', 'data_requests':selected, 'candidates':outcomes}


# Only user-provided text supplies public entities; assistant suggestions are not facts.
TOPICS = {
    'strategy': ('产业政策|行业政策', '产业政策 官方'),
    'market': ('市场|竞品|需求|竞争|防晒|电商|消费者', '市场需求 竞品'),
    'return': ('行业毛利|竞品价格|公开财报', '行业价格 公开财报'),
    'resources': ('开源|依赖|github', '开源依赖'),
    'replication': ('开源许可|软件许可', '开源许可证'),
    'cash': ('汇率|行业账期', '汇率 账期'),
    'risk': ('合规|法规|法律|准入|注册|备案|BPOM|隐私|个人信息|防晒', '准入 法规 官方'),
    'opportunity': ('替代产品|替代工具', '替代产品 对比'),
}
REGIONS = r'中国|国内|印尼|印度尼西亚|马来西亚|泰国|新加坡|越南|美国|欧盟|日本|韩国|英国|澳大利亚'
PRODUCTS = r'防晒(?:霜|乳)?|化妆品|护肤品|食品|医疗器械|保健品|服装|家具|玩具|AI客服|客服助手|知识库|跨境电商|电商|软件'


def rule_plan(project, latest, evidence):
    history = [str(project.get('description', ''))]
    history += [m.get('content', '') for m in project.get('messages', []) if m.get('role') == 'user']
    history.append(latest)
    text = '\n'.join(history)
    regions = re.findall(REGIONS, latest) or re.findall(REGIONS, text)
    regions = list(dict.fromkeys('中国' if r == '国内' else '印尼' if r == '印度尼西亚' else r for r in regions))
    products = re.findall(PRODUCTS, latest, re.I) or re.findall(PRODUCTS, text, re.I)
    # Explicit public product labels support categories outside the common vocabulary.
    labels = re.findall(r'(?:产品|品类|行业)[：:]\s*([\w\u4e00-\u9fff -]{2,24})(?=[，。；\n]|$)', text)
    product = labels[-1] if labels else products[-1] if products else ''
    assistant = next((m.get('content', '') for m in reversed(project.get('messages', [])) if m.get('role') == 'assistant'), '')
    focus = latest + '\n' + assistant
    if not project.get('messages'):
        focus += '\n' + str(project.get('description', ''))
    coverage = (project.get('lifecycle') or {}).get('coverage', {})
    dims = [d for d, (pattern, _) in TOPICS.items() if re.search(pattern, focus, re.I) or coverage.get(d, {}).get('status') == 'external']
    requests, missing = [], []
    for dim in dims:
        if dim in ('resources', 'replication'):
            repos = re.findall(r'https://github\.com/([\w.-]+/[\w.-]+)', text)
            if repos:
                requests.append({'dimension': dim, 'source': 'github', 'query': repos[-1].removesuffix('.git'), 'reason': TOPICS[dim][1]})
            elif re.search(r'开源|软件许可|github', focus, re.I):
                missing.append({'dimension': dim, 'reason': '请提供要核查的开源项目 GitHub 地址'})
            continue
        if not product or len(regions) != 1:
            missing.append({'dimension': dim, 'reason': '请明确本轮核查的产品/品类及一个目标国家地区；多地区需先指定本轮范围'})
            continue
        region = regions[0]
        source = 'law' if dim == 'risk' and region == '中国' else 'web'
        query = product if source == 'law' else f'{region} {product} {TOPICS[dim][1]}'
        requests.append({'dimension': dim, 'source': source, 'query': query, 'reason': TOPICS[dim][1]})
    # Validate all candidates before applying the per-turn cap so cached items do not starve gaps.
    candidates, selected = [], []
    for request in requests:
        plan = plan_requests([request], evidence, latest)
        candidates.extend(plan['candidates'])
        for item in plan['data_requests']:
            if not any(r['source'] == item['source'] and r['query'] == item['query'] for r in selected):
                selected.append(item)
    for candidate in candidates:
        if candidate['status'] == 'selected' and candidate not in selected[:2]:
            # Compare public request fields; validation adds status only to candidates.
            if not any(candidate['source'] == r['source'] and candidate['query'] == r['query'] for r in selected[:2]):
                candidate['status'] = 'deferred'
    return {'method': 'dimension_rules', 'data_requests': selected[:2], 'candidates': candidates, 'missing_parameters': missing}
