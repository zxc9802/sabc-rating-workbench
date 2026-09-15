"""Source-bound scoring and decision fields shared by drafting and review."""
from copy import deepcopy
import json
import math
import re

from sabc.fact_boundaries import qualification
from sabc.rating import upgrade_requirements

VERSION = 1
DECISION_FIELDS = ('business_goal', 'success_metric', 'timeframe', 'maximum_loss')


def sources(project, company, evidence, messages=None):
    result = {'description': project.get('description', ''), 'company': json.dumps(company, ensure_ascii=False)}
    result.update({m.get('id') or f'turn-{i}': m.get('content', '') for i, m in enumerate(
        messages if messages is not None else project.get('messages', [])) if m.get('role') == 'user'})
    superseded = {e.get('supersedes') for e in evidence}
    result.update({'evidence-' + e['id']: e.get('content', '') for e in evidence if e['id'] not in superseded})
    return result


def match_quote(item, texts, user_only=False):
    ident = item.get('source_id', '')
    quote = re.sub(r'\s+', ' ', item.get('quote', '')).strip()
    if user_only and ident != 'description' and not ident.startswith('turn-'):
        return False
    # PDF line wrapping is formatting; words, numbers and their order stay exact.
    text = re.sub(r'\s+', ' ', texts.get(ident, ''))
    if len(quote) < 4 or quote not in text:
        return False
    start = text.find(quote)
    prefix = re.split(r'[。；，,:：]', text[:start])[-1][-16:]
    if re.search(r'不能认定|不能证明|并非|不是|不等于|尚未证实|没有|尚无|未曾|从未|尚未|并未|未$|不$|\b(?:not|no|never|cannot|without)\b', prefix, re.I):
        return False
    return True


def historical_period(value):
    if re.search(r'未来|接下来|计划|希望|(?:报告|发布|季度)(?:后|起)|\d+\s*(?:天|周|个月|月)内', str(value or '')):
        return False
    return bool(re.search(r'财报|业绩报告|报告期间|同比对比|历史(?:资料|数据|期间)', str(value or '')))


def preserve_period(project):
    """Move an explicitly historical period; never invent a future duration."""
    patch = project.get('pending_patch', {})
    value = patch.get('timeframe', project.get('timeframe'))
    if historical_period(value):
        project['data_period'] = value
        project['timeframe'] = None
        patch.pop('timeframe', None)


def validate(proposal, project, company, evidence, messages=None, required=False):
    texts = sources(project, company, evidence, messages)
    strict = required or proposal.get('grounding_version') == VERSION
    if required and proposal.get('grounding_version') != VERSION:
        raise ValueError('新报告及修订必须保留grounding_version=1和来源约束字段')
    scope = proposal.get('assessment_scope') or {}
    if strict and not match_quote(scope, texts, user_only=True):
        raise ValueError('评估主体与范围须引用用户原话，不能由账号公司或模型推断代替')
    if scope.get('level') == 'group' and re.search(r'不是(?:整个)?集团|非集团整体', scope.get('quote', '')):
        raise ValueError('用户排除了集团整体，评估范围不能填group')
    if scope.get('company_baseline'):
        baseline = {'source_id':scope.get('baseline_source_id', ''), 'quote':scope.get('baseline_quote', '')}
        if (not match_quote(baseline, texts, user_only=True)
                or qualification(baseline['quote'], 'known')['knowledge'] in ('unknown', 'not_obtained', 'reported_absent')
                or not re.search(r'公司(?:基线|资料|信息)|账号公司|基线资料', baseline['quote'])
                or re.search(r'不适用|不能|不要|不是', baseline['quote'])):
            raise ValueError('采用账号公司基线须有用户明确确认其适用于被评估主体的原话')
    for key, dimension in proposal.get('dimensions', {}).items():
        score = dimension.get('score')
        direct = []
        for item in dimension.get('support', []):
            if not match_quote(item, texts):
                raise ValueError(f'{key}评分依据须引用实际来源连续原文，不能引用历史助手判断')
            if item['use'] == 'background':
                continue
            if item['scope'] == 'researcher' and project.get('framing', {}).get('purpose') == 'research':
                raise ValueError(f'{key}不能将研究者的资料或预算当作运营方能力')
            if key in ('cash', 'return', 'resources') and item['scope'] in ('group', 'industry') and scope.get('level') != 'group':
                raise ValueError(f'{key}集团或行业财务只能作背景，不能证明业务分部回报或承受能力')
            allocated = re.search(r'(?:已批准|已拨付|已划拨|已授权|确认提供)[^。；\n]{0,16}'
                                  + '(?:本业务|该业务|本项目|' + re.escape(scope.get('subject') or '本业务') + ')', item['quote'])
            if (key in ('cash', 'return', 'resources') and scope.get('level') != 'group'
                    and re.search(r'集团[^。；\n]{0,16}(?:现金|自由现金流|经营现金流|递延收入)', item['quote']) and not allocated):
                raise ValueError(f'{key}引用仍是集团财务口径，不能改标签为分部依据')
            if qualification(item['quote'], 'known')['knowledge'] in ('unknown', 'not_obtained'):
                raise ValueError(f'{key}原文表示未知或资料未取得，只能作背景，不能支持确定分数')
            direct.append(item)
        if strict and score is not None:
            if dimension.get('anchor_score') != math.floor(score) or not direct:
                raise ValueError(f'{key}须填写对应原始分的anchor_score及实际支撑原文；无法判断时保留null，不默认给3分')
    supported_text = '\n'.join(item['quote'] for dim in proposal.get('dimensions', {}).values()
                               for item in dim.get('support', []) if item['use'] == 'support')
    narratives = [dim.get('reason', '') for dim in proposal.get('dimensions', {}).values()]
    narratives += proposal.get('pros', []) + proposal.get('cons', []) + list(proposal.get('decision_brief', {}).values())
    for text in narratives:
        for sentence in re.split(r'[。；\n]', text):
            if re.search(r'不能|不等于|无法认定|未证实|尚未证明', sentence):
                continue
            for claim in re.findall(r'边际零成本|营运资金周转极佳|主要合规与运营风险已被长期管理|现金牛', sentence):
                if claim not in supported_text:
                    raise ValueError('确定性结论“' + claim + '”缺少对应原文依据；须重新判断，不能只加免责声明保留分数')
    if not strict:
        # Legacy drafts retain their shape, but known cross-scope contradictions
        # must not be accepted just because their referenced file exists.
        for key in ('cash', 'return'):
            dim = proposal.get('dimensions', {}).get(key, {})
            if (dim.get('score') is not None and re.search(r'集团', dim.get('reason', ''))
                    and re.search(r'缺少.*(?:分部|订阅业务).*(?:现金|成本|净利润)', dim.get('missing_evidence', ''))):
                raise ValueError(f'{key}缺少本业务财务依据，却使用集团口径评分，须重新对应原文与档位')
        return
    facts = proposal.get('decision_facts', {})
    if set(facts) != set(DECISION_FIELDS):
        raise ValueError('须分别记录经营目标、成功标准、未来周期、最大损失的decision_facts，未知明确填unknown')
    for field, fact in facts.items():
        if fact['kind'] == 'reported':
            if not match_quote(fact, texts, user_only=True) or fact['text'] not in fact['quote']:
                raise ValueError(f'{field}已确认内容须逐字来自用户原话；改写或建议不能冒充用户确认')
            if qualification(fact['quote'], 'known')['knowledge'] in ('unknown', 'not_obtained'):
                raise ValueError(f'{field}用户原话包含未知限定，不能标reported')
            if field == 'timeframe' and historical_period(fact['text']):
                raise ValueError('历史财报期间不能作为未来验证周期')
        elif fact['kind'] == 'suggestion' and not fact['text'].strip():
            raise ValueError(f'{field}建议内容不能为空')
    if len(proposal.get('strongest_objections', [])) != 3:
        raise ValueError('报告须归纳三条最强反对意见，说明它们怎样影响当前判断')


def apply_decision_facts(project, proposal):
    preserve_period(project)
    brief = proposal.setdefault('decision_brief', {})
    brief.update(upgrade_requirements())
    if proposal.get('grounding_version') != VERSION:
        return
    facts = proposal['decision_facts']
    def display(field):
        fact = facts[field]
        if fact['kind'] == 'unknown':
            return '未知，现有资料无法确认'
        return ('建议、待确认：' if fact['kind'] == 'suggestion' else '') + fact['text']
    brief['goal_and_success'] = '经营目标：' + display('business_goal') + '；成功标准：' + display('success_metric')
    brief['maximum_loss'] = display('maximum_loss')
    for field in ('business_goal', 'success_metric', 'timeframe'):
        fact = facts[field]
        project[field] = fact['text'] if fact['kind'] == 'reported' else None
        project.setdefault('pending_patch', {}).pop(field, None)
    project['decision_facts'] = deepcopy(facts)


PROMPT = '''
如果project.report_revision存在，其question是用户提出的复核问题，只表示需要检查的事项，不是新的经营事实；逐项对照原始用户发言和证据修订，不复制报告答疑的结论。缺少新事实时保留未知，不为用户质疑而迎合改分。
报告增加grounding_version=1、assessment_scope、decision_facts、strongest_objections。
assessment_scope={subject:本次被评估的企业或业务名称,level:project/group,source_id,quote}，必须引用用户描述的实际评估范围。业务分部为project，只有评估整个集团才为group；账号公司与研究者不能替代运营主体。
公开研究默认不采用账号公司基线。只有用户明确确认公司基线属于本次被评估运营方时，assessment_scope可加company_baseline=true、baseline_source_id、baseline_quote引用该确认；同名或财报不能替代这项确认。确认后仍逐项检查基线字段和资源约束，不因research一律暂缓，也不因确认而自动授予投入权限。
每个维度增加anchor_score（原始分向下取整对应的正式评分档位；未知为null）和support数组，项为{source_id,quote,subject,scope,metric,period,unit,use}。
source_id用description、company、conversation中的source_id、或evidence-加原始证据ID。quote为对应来源中连续原文，不引用assistant；subject写真实主体，scope只能为project/group/industry/researcher，集团填group，不能写company。metric说明指标，period写原始期间或未注明，unit写原始单位或不适用，use为support/background。引文优先选能保留完整含义的一至两句，不重复整段资料；必须保留决定性的否定、期间和范围，不截掉限制以制造正面事实。
有分数必须有真正支持该档位的support；无法支撑方向时score与anchor_score均null，可保留background。理由逐项解释这些原文如何满足该档位的必要条件。收入/Bookings不是净利润或完整成本模型；集团现金不能证明分部现金健康；数字产品不等于零边际成本；没有违规证据不能证明已有成熟风控。没有不利事实不等于有六七成能力。缺口只能在不影响当前档位必要条件时与该分数并存，否则留空。不得为了保留分数只把事实改成推断。
decision_facts固定四项business_goal/success_metric/timeframe/maximum_loss，每项{text,kind,source_id,quote}。kind=reported/suggestion/unknown；reported的text必须是quote中的连续子串，不能改写、概括或拼接多个句子。保留适用对象和完整限定。未来目标、预算或损失不能由财报代为确认。示例：用户说“管理层没有提供观察周期”，timeframe必须为{"kind":"unknown","text":"","source_id":"","quote":""}，不能标reported或填财报季度。模型提出的阈值用suggestion，不能回写为已确认目标。历史资料期间与未来验证周期分开；90天回访建议不等于确认周期。
报告摘要、正反方、验证条件必须与上述同一组事实一致。每次使用集团数据都标集团范围；所有模型新设的数值阈值每次出现均标建议、待确认。关键评分必要条件缺失时，不用免责声明保留确定结论。strongest_objections必须是恰好三条字符串组成的数组：["反对理由及能否化解的判断","第二条理由与判断","第三条理由与判断"]，不能输出对象数组或额外的证据ID字段。
升级A/S的通用条件由程序根据固定规则生成；不要另造门槛或把本次范围缩小为单个产品。模型只在验证任务中描述本项目的补证办法，不把可选验证路径写成新的通用规则。
'''
