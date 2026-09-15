"""Per-dimension interview checkpoints, grounded in supplied source text."""
import json
import re
from datetime import date
from sabc.business_time import today
from sabc.rating import PROJECT_FIELDS
from sabc.fact_boundaries import qualification, complete_quote

CHECKS = {
    'strategy': {'purpose': '这个项目想改善什么经营结果？', 'fit': '它与公司当前优先事项有什么联系？', 'timing': '为什么现在做这个项目？'},
    'market': {'user': '具体服务谁、解决什么问题？', 'need': '需求的频次和影响有什么依据？', 'alternative': '目标用户现在怎样解决这个问题，你的方案有何不同？'},
    'return': {'value': '收入或提效价值具体怎样兑现？',
               'validation_history': '这个项目已经做过测试、试点或实际运行吗？',
               'validation_results': '已有测试是在什么时间、什么样本范围做的，实际效果和成本怎样，哪些结果仍不清楚？',
               'validation_records': '这些测试结果有什么记录、由谁核对，能提供哪些材料或明确哪些无法提供？',
               'validation_transfer': '有没有可参考的类似项目实绩？如果有，哪些条件与本项目相同或不同，有什么依据？',
               'metric_formula': '收益或ROI指标的具体计算公式是什么，分子和分母包括什么？', 'costs': '需要扣除哪些持续成本，哪些金额仍未知？', 'success': '达到什么指标才算值得继续？'},
    'resources': {'owner': '谁负责执行、具备哪些能力？', 'capacity': '实际能投入多少人员时间，会影响现有业务吗？', 'dependencies': '还需哪些外包、资料或接入条件，落实情况如何？'},
    'replication': {'assets': '项目能留下哪些可复用的资产？', 'scope': '以后准备复用到什么场景？', 'extra': '扩大范围还需增加哪些投入？'},
    'cash': {'initial': '初期核查与执行分别准备投入多少钱？', 'ongoing': '持续现金支出怎样安排？', 'timing': '回款或节省兑现时间怎样安排？', 'investment_limit': '整个项目的总投入上限是多少？', 'max_loss': '最多能承受多少不可回收损失？'},
    'risk': {'failure': '哪些情况会使项目失败，达到什么条件停止？', 'control': '停止后如何退出、控制损失？', 'compliance': '本项目适用的数据、产品或经营合规条件有哪些，如何处理？'},
    'opportunity': {'options': '不做、延后或采用现成方案，分别有什么影响？', 'comparison': '与可行替代方案相比，为什么选择这个方案？', 'tradeoff': '会占用哪些现有业务或其他项目的资源？'},
}
RESOLVED = ('known', 'unknown', 'external', 'future')
SHORT_UNKNOWN = re.compile(r'(?:我)?(?:不知道|不清楚|无法提供|不能提供|没有拿到)[。！!]?\s*')
UNAVAILABLE = re.compile(r'不知道|不清楚|未知|未定|没定|未确认|待确认|未(?:取得|获取|获得|拿到)|尚未|还没|没有|没做|没问|未询价|未(?:经|做|完成)?(?:书面|独立|正式)?(?:核验|核查|验证|询价|报价|确认|落实)|待验证|待核|无法|不能提供|需要.*(?:核查|验证|试验)|预计|预估|估算|假设')
TEST_TOPIC = r'测试|试点|试运行|试验|实测|实际(?:运行|运营)|商业化(?:运行|运营)?|真实订单|真实成交|付费客户'


def no_test(quote):
    if re.search(r'但是|不过|更正|其实|现在已经', quote):
        return False
    return bool(re.fullmatch(r'没做过[。！!]?|没有[。！!]?', quote) or re.search(
        r'(?:^|[。；，,\n]|(?:本|这个|该)(?:项目|方案))\s*(?:目前|我们|我)?\s*'
        r'(?:还没有|还没|没|尚未|从未|未|没有)(?:做过|做|进行过|进行|开展过|开展|开始)?'
        r'(?:任何|实际|小规模)?(?:测试|试点|试运行|试验|实测)(?:过)?(?=[。；，,！!]|$)', quote))


def validation_answer(key, quote, status, source, dialogue):
    if source not in ('user', 'evidence'):
        return False
    if key == 'validation_history':
        linked = any(m.get('role') == 'user' and m.get('content', '').strip() == quote
                     and i > 0 and dialogue[i - 1].get('role') == 'assistant'
                     and re.search(TEST_TOPIC, dialogue[i - 1].get('content', ''))
                     for i, m in enumerate(dialogue))
        if len(quote.rstrip('。！!')) <= 4:
            return linked and quote.rstrip('。！!') in ('没做过', '没有', '做过', '有', '不知道', '不清楚')
        period = re.search(r'(?:测试|试点|试验)(?:是在|是|在|时间为)(\d{4})年(\d{1,2})月(\d{1,2})日', quote)
        dated_sample = False
        if period and re.search(r'(?:共|覆盖).*\d+\s*(?:条|单|笔|人|件|样本)', quote):
            try:
                dated_sample = date(*map(int, period.groups())) <= today()
            except ValueError:
                pass
        return bool(re.search(TEST_TOPIC, quote) and (no_test(quote)
                    or (status != 'known' and re.search(r'不知道|不清楚|未知|无法确认', quote)
                        and re.search(r'是否|有没有|做没做|测没测|测试情况|试点情况|测试经历|做过.*[吗?？]', quote))
                    or (not re.search(r'计划|目标|预计|希望|假设|将要|准备|未来', quote)
                        and (dated_sample or re.search(r'(?:测试|试点|试运行|试验)(?:过|了)|(?:做过|进行过|开展过|完成过)(?:(?:本|这个|该)(?:项目|方案))?的?(?:测试|试点|试运行|试验)|已经|曾经|实际|实测|上周|上月|去年', quote)))))
    topics = {'validation_results': r'测试|试点|试验|实测|结果|效果|样本',
              'validation_records': r'测试|记录|日志|报表|凭证|材料|核对|复核',
              'validation_transfer': r'类似|同类|其他项目|别的项目|其他店铺|可迁移|成功案例'}
    if quote.rstrip('。！!') in ('不知道', '不清楚', '无法提供', '没有'):
        return any(m.get('role') == 'user' and m.get('content', '').strip() == quote
                   and i > 0 and dialogue[i - 1].get('role') == 'assistant'
                   and re.search(topics[key], dialogue[i - 1].get('content', ''))
                   for i, m in enumerate(dialogue))
    if status != 'known':
        return bool(re.search(topics[key], quote))
    if key == 'validation_results':
        return bool(re.search(r'\d|[零一二三四五六七八九十百千万]+', quote)
                    and re.search(r'结果|效果|收入|利润|成本|耗时|工时|小时|错误|漏检|误报|转化|成交|销量|售出', quote)
                    and not re.search(r'目标|计划|预计|预估|希望|假设', quote))
    if key == 'validation_records':
        return bool(re.search(r'记录|日志|报表|账单|凭证|材料|附件|文件|核对|复核|抽查', quote))
    return bool(re.search(topics[key], quote)
                and (re.search(r'没有|不知道|不清楚|无法提供', quote)
                     or (re.search(r'\d', quote) and re.search(r'相同|不同|差异|一致|不能照搬', quote))))


def complete(items, dimension):
    return all(items.get(key, {}).get('verified') is True
               and items[key].get('status') in RESOLVED for key in CHECKS[dimension])


def explicit_unavailable(key, message):
    # Narrow fallback for explicit answers the model repeatedly left as questions.
    # Never infer other checkpoints (ROI, personnel, budgets) from these unknowns.
    patterns = {
        'costs': (r'持续成本|持续费用|单件成本|全部成本', r'未知|不知道|无法提供|没有报价'),
        'dependencies': (r'外包|依赖|代理', r'均未落实|都未落实|全部未落实|均未确认|均未确定'),
        'extra': (r'(?:迁移|扩大|复制|扩店).*(?:成本|费用|投入|工时)', r'未知|不知道|无法提供|没有报价'),
        'investment_limit': (r'总投入|总预算|投入上限|预算上限', r'未知|不知道|不清楚|未(?:取得|获取|获得|拿到)|无法(?:提供|取得)'),
        'max_loss': (r'损失|亏损|亏|赔', r'未知|不知道|不清楚|未(?:取得|获取|获得|拿到)|无法(?:提供|取得)'),
    }
    if key not in patterns:
        return ''
    topic, unavailable = patterns[key]
    for sentence in reversed(re.split(r'[。；\n]', message)):
        if re.search(r'[？?]|并非|不是|不再|之前|此前|原来|曾经|过去|已落实|已确认|已确定', sentence):
            continue
        if re.search(topic, sentence) and re.search(unavailable, sentence):
            if key in ('investment_limit', 'max_loss') and re.search(r'\d+\s*(?:万|千|元|块)', sentence):
                continue
            return sentence.strip()
    return ''


def last_question(messages):
    index = next((i for i in range(len(messages) - 1, -1, -1) if messages[i].get('role') == 'user'), -1)
    return messages[index - 1] if index > 0 and messages[index - 1].get('role') == 'assistant' else {}


def changed_answer(key, quote, prior):
    if quote == prior.get('quote') or not re.search(r'更正|纠正|改为|改成|不再|变化|改变|重新|有冲突|不一致|说错|不准确|现在(?:已|要|用于)', quote):
        return False
    topic = {'purpose': r'目的|用途|报告|研究|归档|发布|投资|采购',
             'fit': r'战略|优先|主业|公司', 'timing': r'时间|现在|回款|兑现|延后|提前',
             'user': r'用户|客户|商家|人群', 'need': r'需求|频次|影响',
             'alternative': r'替代|原来|现有|软件|外包|美工',
             'value': r'收入|价值|提效|收费|订阅|兑现',
             'validation_history': TEST_TOPIC, 'validation_results': r'实测|测试|试点|结果|效果',
             'validation_records': r'记录|材料|核对|核验', 'validation_transfer': r'类似|同类|迁移|案例',
             'metric_formula': r'公式|分子|分母|ROI|工时|收益', 'costs': r'成本|费用', 'success': r'成功|达标|指标|阈值',
             'owner': r'负责|执行|维护|技术|人员', 'capacity': r'人员|人手|工时|时间|排期',
             'dependencies': r'依赖|外包|接入|资料|权限', 'assets': r'资产|数据|模板|模型|SOP',
             'scope': r'范围|扩|复制|场景', 'extra': r'迁移|扩|复制|新增',
             'initial': r'首期|初期|预算|投入', 'ongoing': r'持续|每月|订阅|现金支出',
             'investment_limit': r'总投入|总预算|投入上限|预算上限',
             'max_loss': r'损失|亏损|亏|赔', 'failure': r'失败|停止|止损|超标|不达标',
             'control': r'退出|停止|损失|权限|回退', 'compliance': r'合规|授权|版权|法规|准入',
             'options': r'不做|延后|替代|现成', 'comparison': r'对比|比较|替代|选择|方案',
             'tradeoff': r'主业|资源|占用|优先|其他项目'}.get(key)
    return bool(topic and re.search(topic, quote))


def question_subject(project, target):
    return 'operator' if project.get('framing', {}).get('purpose') == 'research' and target in ('cash.investment_limit', 'cash.max_loss') else 'project'


def question_reply(reply, old_questions, questions):
    # Keep document explanations, but only show questions that survived the gate.
    for question in old_questions:
        if question.strip():
            reply = reply.replace(question, '')
    statements = [s.strip() for s in re.findall(r'[^。！？?！\n]+[。！？?！]?', reply)
                  if s.strip() and not re.search(r'[？?]|^(?:请问|请补充|另外[，,]?$)', s.strip())
                  and not re.search(r'(?:问答|信息|八维|收集).*(?:已完成|已.*完毕)|正在整理报告|现在生成报告|(?:剩下|还有|先核实|能看|需要确认).*[一二两三四五六七八九十\d]+.*(?:件事|个|项)', s)
                  and not re.fullmatch(r'[（）()：:\s]+', s.strip())]
    text = '\n\n'.join(statements + questions)
    for opening, closing in (('（', '）'), ('(', ')')):
        if text.count(opening) != text.count(closing):
            text = text.replace(opening, '').replace(closing, '')
    return text


def normalize(result, project, company, evidence, messages):
    project = {**project, 'framing': result.get('framing') or project.get('framing') or {}}
    history = project.get('messages', [])
    # Production supplies full history; older callers may supply only new turns.
    dialogue = messages if messages[:len(history)] == history else history + messages
    user_sources = [str(project.get('description', ''))] + [m.get('content', '') for m in dialogue if m.get('role') == 'user']
    user = '\n'.join(user_sources)
    sources = {'user': user, 'company': json.dumps(company, ensure_ascii=False),
               'project': json.dumps({k: project[k] for k in PROJECT_FIELDS if k in project}, ensure_ascii=False),
               'evidence': '\n'.join(str(e.get('content', '')) for e in evidence)}
    latest_user = next((m.get('content', '') for m in reversed(messages) if m.get('role') == 'user'), '')
    asked = last_question(dialogue).get('question_targets', [])
    previous = project.get('lifecycle', {}).get('coverage', {})
    coverage = result.get('dimension_coverage') or {}
    pending = []
    rejected = []
    for dimension, checks in CHECKS.items():
        entry = coverage.setdefault(dimension, {})
        raw = entry.get('items') or {}
        items = {}
        for key, question in checks.items():
            target = dimension + '.' + key
            candidate = raw.get(key) or {}
            history = items.get('validation_history', {})
            skipped_test = key in ('validation_results', 'validation_records') and history.get('verified') and no_test(history['quote'])
            if skipped_test:
                candidate = {'status': 'future', 'source': history['source'], 'quote': history['quote']}
            quote = str(candidate.get('quote', '')).strip()
            source = candidate.get('source', 'user')
            status = candidate.get('status', 'ask')
            if source == 'user' and question_subject(project, target) == 'operator':
                quote = complete_quote(quote, user_sources)
            grounded = len(quote) >= (2 if status in ('unknown', 'external', 'future') else 4) and quote in sources.get(source, '')
            # An unavailable fact must be acknowledged by the user, never inferred from silence.
            if status in ('unknown', 'external', 'future'):
                grounded = grounded and source == 'user' and bool(UNAVAILABLE.search(quote))
            if key.startswith('validation_') and not skipped_test:
                grounded = (bool(quote and quote in sources.get(source, ''))
                            and validation_answer(key, quote, status, source, dialogue)
                            and (status == 'known' or (source == 'user' and bool(UNAVAILABLE.search(quote)))))
                if key in ('validation_results', 'validation_records') and len(quote.rstrip('。！!')) > 4 and no_test(quote):
                    grounded = False
            # verified means source text matched, not that a business claim is independently proven.
            scope = {'investment_limit': r'总投入|总预算|投入上限|预算上限|总(?:项目)?现金(?:占用|投入)?上限|最多投入|最多花|总额|不超过',
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
            time_formula = bool(re.search(
                r'(?:原|旧|基线|改造前|上线前)[^。；\n]*?(?:工时|耗时|小时|分钟)'
                r'[^。；\n]*?(?:减去|减|-|−)[^。；\n]*?(?:新|试点|实际|上线后|改造后)'
                r'[^。；\n]*?(?:工时|耗时|小时|分钟)', quote))
            if key == 'metric_formula' and re.search(r'ROI|投产比', user, re.I) and not time_formula:
                grounded = grounded and bool(re.search(r'ROI|ROAS|投入收益率|投产比|分子|分母', quote, re.I))
                if status == 'known':
                    grounded = grounded and bool(re.search(r'除以|÷|/|分子|分母|销售额.*(?:除|成本|费用)|收入.*(?:除|成本|费用)', quote))
            prior = previous.get(dimension, {}).get('items', {}).get(key, {})
            previous_history = previous.get(dimension, {}).get('items', {}).get('validation_history', {})
            if (key in ('validation_results', 'validation_records') and not skipped_test
                    and prior.get('quote') == previous_history.get('quote') and no_test(prior.get('quote', ''))):
                prior = {}  # A new test needs its own results; old "not tested" cannot close it.
            prior_quote = str(prior.get('quote', '')).strip()
            if prior.get('source') == 'user' and question_subject(project, target) == 'operator':
                prior_quote = complete_quote(prior_quote, user_sources)
            declared = explicit_unavailable(key, latest_user)
            if asked == [target] and SHORT_UNKNOWN.fullmatch(latest_user):
                declared = latest_user.strip()
            if (status == 'ask' or not grounded or question_subject(project, target) == 'operator') and declared:
                quote, source, status, grounded = declared, 'user', 'unknown', True
            if (source == 'user' and quote == latest_user.strip() and SHORT_UNKNOWN.fullmatch(quote)
                    and 'question_targets' in last_question(dialogue)):
                grounded = grounded and asked == [target]
            meaning = qualification(quote, status)
            if source == 'user' and question_subject(project, target) == 'operator' and meaning['subject'] in ('researcher', 'mixed'):
                grounded = False
            if key.startswith('validation_') and source == 'user' and meaning['knowledge'] in ('not_obtained', 'unknown') and grounded:
                status = 'unknown'
            # A model omission/paraphrase cannot erase a previously grounded answer.
            # A quoted change in the latest user turn may reopen it for clarification.
            if ((not grounded or status not in RESOLVED) and prior.get('verified') is True and prior.get('status') in RESOLVED
                    and prior_quote and prior_quote in sources.get(prior.get('source'), '')
                    and not (question_subject(project, target) == 'operator' and qualification(prior_quote, prior['status'])['subject'] in ('researcher', 'mixed'))
                    and not (source == 'user' and len(quote) >= 2 and quote in latest_user and changed_answer(key, quote, prior))):
                quote, source, status = prior_quote, prior['source'], prior['status']
                grounded = True
            verified = bool(grounded and status in RESOLVED)
            if not verified:
                rejected.append({'dimension': dimension, 'checkpoint': key, 'status': status,
                                 'source': source, 'quote_length': len(quote),
                                 'returned': key in raw, 'returned_keys': list(raw),
                                 'source_match': bool(quote and quote in sources.get(source, '')),
                                 'user_match': bool(quote and quote in user),
                                 'unavailable_word': bool(UNAVAILABLE.search(quote))})
            items[key] = {'status': status if verified else 'ask', 'source': source,
                          'quote': quote if verified else '', 'verified': verified}
            if verified:
                items[key].update(qualification(quote, status))
            if not verified:
                # Ask whether a test exists before asking for its results or records.
                if key not in ('validation_results', 'validation_records') or history.get('verified'):
                    pending.append((target, ('运营方' if question_subject(project, target) == 'operator' else '') + question))
        entry['items'] = items
        entry['status'] = next((item['status'] for item in items.values() if item['status'] != 'known'), 'known') if complete(items, dimension) else 'ask'
        entry['reason'] = entry.get('reason') or '仍需补充项目依据'
    result['dimension_coverage'] = coverage
    # The same grounded answer must reach the required project field as well as progress.
    target = coverage.get('market', {}).get('items', {}).get('user', {})
    facts = {**project, **project.get('pending_patch', {}), **result.get('project_patch', {})}
    if (not facts.get('target_user') and target.get('verified') and target.get('status') == 'known'
            and target.get('source') == 'user'):
        result.setdefault('project_patch', {})['target_user'] = target['quote']
    if rejected:
        from sabc.model_router import audit
        if audit.get():
            audit.get()({'role': 'collection_validation', 'status': 'rejected', 'checks': rejected})
    targets, original = result.get('question_targets', []), result.get('questions', [])
    allowed = dict(pending)
    selected = {}
    if len(targets) == len(original):
        for target, question in zip(targets, original):
            if target in allowed and question.strip() and target not in selected:
                selected[target] = question
    selected = selected or dict(pending[:2])
    result['question_targets'] = list(selected)
    result['questions'] = list(selected.values())
    if result['questions']:
        result['reply'] = question_reply(result.get('reply', ''), original, result['questions'])
    if not pending:
        result['questions'] = []
        result['question_targets'] = []
        result['reply'] = '信息已整理完成，现在生成报告吗？'
        result['reply_evidence_ids'] = []
        result['data_requests'] = []
    return result


PROMPT = '''
八维收口须逐项检查，不能把本轮只追问两项理解成只剩两个缺口。
每个dimension_coverage条目增加items，必须填写下列对应检查项：
''' + json.dumps(CHECKS, ensure_ascii=False) + '''
每项结构为{"status":"known/ask/unknown/external/future","source":"user/company/project/evidence","quote":"来源中的连续原文"}。
已回答用known并引用具体依据；尚未问过或没有依据用ask、quote为空。unknown仅在用户明确无法回答该项时使用；external/future也须用户明确承认该项待核查/验证，引用其原话。不能凭缺少信息关闭问题。
测试经历是必查项：validation_history先核实本项目是否已经测试、试点或实际运行。用户没提过不等于没做过；未来计划、目标值、没有日志或没有报价都不能替代测试经历的回答。已明确说明的直接引用，不重复问。
如果已经测试过，validation_results要逐步问清测试时间、样本量和适用范围、对照基线与实际效果、全部适用成本及准确性指标；只说“做过”“效果不错”不够。按项目追问用户能回答的缺口，不一口气问成长表单。实际结果与目标分开引用；实测结果引用里不混入未来目标。某项记不清就明确记录该项未知，不能把其他已经知道的结果一起清空。
validation_records确认记录是什么、来源和核对人、是否能提供；只有口述或记录遗失时保留自述及局限，不冒充已核验。没有上传文件不能推断没有测试；上传也不等于核验通过。用户明确本项目未测试时，validation_results和validation_records用future引用同一句未测试原话，不索要尚不存在的结果。
validation_transfer另问是否有可参考的类似项目实绩；本项目未测试不代表没有类似经验。有案例则问清结果、记录来源、相同条件和不可直接迁移的差异；没有或无法提供就引用用户原话保留未知。不因一句“有成功案例”直接关闭该项或升级证据。
items记录的是该项是否已交流处理，不是业务条件是否已实现。列明成本种类并说金额未知，return.costs必须为unknown，引用包括“未知”的该句；列明外包对象并说均未落实，resources.dependencies必须为unknown或external，不能继续ask要求其给报价、落实人员或决定样品方案。具体方案尚未决定也是明确未知；不以补全试点执行细节作为生成报告前提，报告可暂缓评级并列待核查任务。
未知必须对应具体检查项：成本金额未知不能关闭价值兑现路径、收益公式、成功指标或总投入上限；只说外包费用未知，也不能推断负责人、内部工时或外包落实情况。问到的新事项若用户明确说尚未决定/无法提供，记录对应未知，不能换说法要求立即作决定。
每个检查项独立判断：投入上限必须是用户明确承诺的总额，最大损失必须是可承受的损失金额，清货动作不能替代损失上限；ROI目标值和列举费用不能替代分子分母定义。报价未知不等于投入上限未知，效果待验证不等于成功标准未定；一个未知不能替代整维其他问题。引用必须真正支持当前检查项，不能用泛泛的项目意愿填充预算、资源等项。
按项目类型理解问题：内部项目看产能/成本和内部需求，不强问销售收入；不适用的事项用known，引用能说明不适用的事实，不凭空宣称不适用。已有资料或用户一次回答涵盖多项可直接引用，不重复问。
用户明确当前不扩店/不扩大范围，replication.scope用known引用当前范围边界；迁移额外成本或工时明确未知时extra用unknown，不要求选下一家店或编造扩张计划。没有扩大计划不等于已验证可复制，评级仍按现有证据判断。
人员可调用排期是资源上限，不等于实际新增耗时。净节省只用新旧流程实际全员总工时比较，不能把可调用时间再当实际投入重复相减。已明确总工时覆盖复核、返工和维护时，不为完善执行细节强制追问每个人每项细分；只有具体资源冲突才继续问。
当前流程和改进方向明确后，若validation_history仍未回答，优先问是否已做过测试，再讨论未来试点指标与执行细节；不等所有其他检查项问完才追回测试经历。
先用最新用户回答更新检查项，再从更新后的缺口提问；上一轮已问且本轮已答的止损、替代方案等不能原样再问。若历史测试问题被用户漏答，且本轮也未回答，应优先追回该遗漏。
继承仍有效的历史items原文，但有新信息冲突时更新。全量返回检查项，短引用即可，避免长篇解释。每轮从尚未解决的检查项选择最多两个单一主题问题，优先现金约束、价值和明显风险；逐渐覆盖其他维度，不集中重复打磨某项。
补充一项不能抹掉其他已处理项；此前明确未知也不重新索要。只有最新用户原话改变或否定此前依据，才将该项重开为ask，并在quote引用这句新的冲突原文；不能因为本轮没有再次提及而重开。明确更正的金额或公式直接使用新原文更新，不保留被替代的旧值。
只有所有检查项均处理完且questions为空才询问是否生成报告；普通访谈不生成proposal或stage_review，不启动独立审查。
有questions时同时给出等长question_targets，每项为对应检查项的dimension.checkpoint，如cash.max_loss；程序会移除已处理事项的重复追问。每个问题只对应一个尚未解决的主题。
上一轮assistant的question_targets说明当时问的是哪些事项；“不知道”等短答只在指向明确时绑定，问了两项只回答一项不能关闭另一项。reply只展示本轮questions中的问题，不在正文夹带额外追问。
研究者本人投入和被研究产品的运营投入分别记录。purpose=research时，cash.investment_limit/max_loss针对运营方；个人研究预算或零现金损失不能充当运营方额度，无法得知就记录对应未知。
quote保留完整主语、否定和范围：“我未取得实测记录”不等于“运营方未做过实测”，“不知道授权情况”不等于“没有授权”。历史items中的knowledge/subject是程序派生的来源限定，不是额外证据；输出不必填写这些字段。
'''
