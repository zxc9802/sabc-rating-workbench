"""Per-dimension interview checkpoints, grounded in supplied source text."""
import json
import re
from sabc.rating import PROJECT_FIELDS

CHECKS = {
    'strategy': {'purpose': '这个项目想改善什么经营结果？', 'fit': '它与公司当前优先事项有什么联系？', 'timing': '为什么现在做这个项目？'},
    'market': {'user': '具体服务谁、解决什么问题？', 'need': '需求的频次和影响有什么依据？', 'alternative': '目标用户现在怎样解决这个问题，你的方案有何不同？'},
    'return': {'value': '收入或提效价值具体怎样兑现？', 'metric_formula': '收益或ROI指标的具体计算公式是什么，分子和分母包括什么？', 'costs': '需要扣除哪些持续成本，哪些金额仍未知？', 'success': '达到什么指标才算值得继续？'},
    'resources': {'owner': '谁负责执行、具备哪些能力？', 'capacity': '实际能投入多少人员时间，会影响现有业务吗？', 'dependencies': '还需哪些外包、资料或接入条件，落实情况如何？'},
    'replication': {'assets': '项目能留下哪些可复用的资产？', 'scope': '以后准备复用到什么场景？', 'extra': '扩大范围还需增加哪些投入？'},
    'cash': {'initial': '初期核查与执行分别准备投入多少钱？', 'ongoing': '持续现金支出怎样安排？', 'timing': '回款或节省兑现时间怎样安排？', 'investment_limit': '整个项目的总投入上限是多少？', 'max_loss': '最多能承受多少不可回收损失？'},
    'risk': {'failure': '哪些情况会使项目失败，达到什么条件停止？', 'control': '停止后如何退出、控制损失？', 'compliance': '本项目适用的数据、产品或经营合规条件有哪些，如何处理？'},
    'opportunity': {'options': '不做、延后或采用现成方案，分别有什么影响？', 'comparison': '与可行替代方案相比，为什么选择这个方案？', 'tradeoff': '会占用哪些现有业务或其他项目的资源？'},
}
RESOLVED = ('known', 'unknown', 'external', 'future')
UNAVAILABLE = re.compile(r'不知道|不清楚|未知|未定|没定|未确认|待确认|尚未|还没|没有|没做|没问|未询价|未(?:经|做|完成)?(?:书面|独立|正式)?(?:核验|核查|验证|询价|报价|确认|落实)|待验证|待核|无法|不能提供|需要.*(?:核查|验证|试验)|预计|预估|估算|假设')


def complete(items, dimension):
    return all(items.get(key, {}).get('verified') is True
               and items[key].get('status') in RESOLVED for key in CHECKS[dimension])


def normalize(result, project, company, evidence, messages):
    user = '\n'.join([str(project.get('description', ''))] +
                     [m.get('content', '') for m in project.get('messages', []) + messages if m.get('role') == 'user'])
    sources = {'user': user, 'company': json.dumps(company, ensure_ascii=False),
               'project': json.dumps({k: project[k] for k in PROJECT_FIELDS if k in project}, ensure_ascii=False),
               'evidence': '\n'.join(str(e.get('content', '')) for e in evidence)}
    dialogue = project.get('messages', []) + messages
    latest_user = next((m.get('content', '') for m in reversed(messages) if m.get('role') == 'user'), '')
    previous = project.get('lifecycle', {}).get('coverage', {})
    coverage = result.get('dimension_coverage') or {}
    pending = []
    rejected = []
    for dimension, checks in CHECKS.items():
        entry = coverage.setdefault(dimension, {})
        raw = entry.get('items') or {}
        items = {}
        for key, question in checks.items():
            candidate = raw.get(key) or {}
            quote = str(candidate.get('quote', '')).strip()
            source = candidate.get('source', 'user')
            status = candidate.get('status', 'ask')
            grounded = len(quote) >= (2 if status in ('unknown', 'external', 'future') else 4) and quote in sources.get(source, '')
            # An unavailable fact must be acknowledged by the user, never inferred from silence.
            if status in ('unknown', 'external', 'future'):
                grounded = grounded and source == 'user' and bool(UNAVAILABLE.search(quote))
            # verified means source text matched, not that a business claim is independently proven.
            scope = {'investment_limit': r'总投入|总预算|投入上限|预算上限|最多投入|最多花|总额|不超过',
                     'max_loss': r'损失|亏损|亏|赔'}.get(key)
            if scope:
                linked = any(m.get('role') == 'user' and quote and quote in m.get('content', '')
                             and i > 0 and dialogue[i-1].get('role') == 'assistant'
                             and re.search(scope, dialogue[i-1].get('content', ''))
                             for i, m in enumerate(dialogue))
                grounded = (grounded or (linked and len(quote) >= 2)) and bool(re.search(scope, quote) or linked)
                if status in ('unknown', 'external', 'future'):
                    grounded = grounded and source == 'user' and bool(UNAVAILABLE.search(quote))
                if status == 'known':
                    grounded = grounded and bool(re.search(r'(?:\d+(?:\.\d+)?|[零一二三四五六七八九十百千万两]+)\s*(?:万|千|元|块)|(?:损失|预算|投入)(?:为|是)?[零0]|无现金支出', quote))
            if key == 'metric_formula' and re.search(r'ROI|投产比', user, re.I):
                grounded = grounded and bool(re.search(r'ROI|ROAS|投入收益率|投产比|分子|分母', quote, re.I))
                if status == 'known':
                    grounded = grounded and bool(re.search(r'除以|÷|/|分子|分母|销售额.*(?:除|成本|费用)|收入.*(?:除|成本|费用)', quote))
            prior = previous.get(dimension, {}).get('items', {}).get(key, {})
            prior_quote = str(prior.get('quote', '')).strip()
            # A model omission/paraphrase cannot erase a previously grounded answer.
            # A quoted change in the latest user turn may reopen it for clarification.
            if (not grounded and prior.get('verified') is True and prior.get('status') in RESOLVED
                    and prior_quote and prior_quote in sources.get(prior.get('source'), '')
                    and not (source == 'user' and len(quote) >= 2 and quote in latest_user)):
                quote, source, status = prior_quote, prior['source'], prior['status']
                grounded = True
            verified = bool(grounded and status in RESOLVED)
            if not verified and status != 'ask':
                rejected.append({'dimension': dimension, 'checkpoint': key, 'status': status,
                                 'source': source, 'quote_length': len(quote),
                                 'source_match': bool(quote and quote in sources.get(source, '')),
                                 'user_match': bool(quote and quote in user),
                                 'unavailable_word': bool(UNAVAILABLE.search(quote))})
            items[key] = {'status': status if verified else 'ask', 'source': source,
                          'quote': quote if verified else '', 'verified': verified}
            if not verified:
                pending.append(question)
        entry['items'] = items
        entry['status'] = next((item['status'] for item in items.values() if item['status'] != 'known'), 'known') if complete(items, dimension) else 'ask'
        entry['reason'] = entry.get('reason') or '仍需补充项目依据'
    result['dimension_coverage'] = coverage
    if rejected:
        from sabc.model_router import audit
        if audit.get():
            audit.get()({'role': 'collection_validation', 'status': 'rejected', 'checks': rejected})
    if not pending:
        result['questions'] = []
        result['reply'] = '信息已整理完成，现在生成报告吗？'
        result['reply_evidence_ids'] = []
        result['data_requests'] = []
    elif not result.get('questions'):
        result['questions'] = pending[:2]
        result['reply'] = '\n\n'.join(pending[:2])
        result['needs_external_action'] = False
    return result


PROMPT = '''
八维收口须逐项检查，不能把本轮只追问两项理解成只剩两个缺口。
每个dimension_coverage条目增加items，必须填写下列对应检查项：
''' + json.dumps(CHECKS, ensure_ascii=False) + '''
每项结构为{"status":"known/ask/unknown/external/future","source":"user/company/project/evidence","quote":"来源中的连续原文"}。
已回答用known并引用具体依据；尚未问过或没有依据用ask、quote为空。unknown仅在用户明确无法回答该项时使用；external/future也须用户明确承认该项待核查/验证，引用其原话。不能凭缺少信息关闭问题。
每个检查项独立判断：投入上限必须是用户明确承诺的总额，最大损失必须是可承受的损失金额，清货动作不能替代损失上限；ROI目标值和列举费用不能替代分子分母定义。报价未知不等于投入上限未知，效果待验证不等于成功标准未定；一个未知不能替代整维其他问题。引用必须真正支持当前检查项，不能用泛泛的项目意愿填充预算、资源等项。
按项目类型理解问题：内部项目看产能/成本和内部需求，不强问销售收入；不适用的事项用known，引用能说明不适用的事实，不凭空宣称不适用。已有资料或用户一次回答涵盖多项可直接引用，不重复问。
继承仍有效的历史items原文，但有新信息冲突时更新。全量返回检查项，短引用即可，避免长篇解释。每轮从尚未解决的检查项选择最多两个单一主题问题，优先现金约束、价值和明显风险；逐渐覆盖其他维度，不集中重复打磨某项。
补充一项不能抹掉其他已处理项；此前明确未知也不重新索要。只有最新用户原话改变或否定此前依据，才将该项重开为ask，并在quote引用这句新的冲突原文；不能因为本轮没有再次提及而重开。明确更正的金额或公式直接使用新原文更新，不保留被替代的旧值。
只有所有检查项均处理完且questions为空才询问是否生成报告；普通访谈不生成proposal或stage_review，不启动独立审查。
'''
