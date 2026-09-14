"""Preserve who a statement concerns and what its source actually establishes."""
import re

from sabc.rating import DIMENSIONS

NOT_OBTAINED = re.compile(r'未(?:取得|获取|拿到|检索到)|尚未找到|没有?(?:取得|拿到|获取|找到|收到)|'
                          r'(?:没有|未)(?:向|给)(?:我们|我|本人|研究者)[^。；\n]*?提供|'
                          r'现有(?:资料|材料|信息).*?(?:没有|不含)|我没有.*?(?:记录|材料|资料|报表)')
UNKNOWN = re.compile(r'不知道|不清楚|不了解|未知|无法(?:确认|判断|提供|取得)|不能提供')
ABSENT = re.compile(r'不存在|(?:没有|尚无|未做过|没做过|从未|尚未做|尚未进行)|(?:^|[，,；。])无')


def qualification(quote, status):
    # This describes a source claim, never independent verification of that claim.
    if NOT_OBTAINED.search(quote):
        kind = 'not_obtained'
    elif UNKNOWN.search(quote):
        kind = 'unknown'
    elif ABSENT.search(quote):
        kind = 'reported_absent'
    elif status in ('external', 'future'):
        kind = 'unverified'
    elif status == 'unknown':
        kind = 'unknown'
    else:
        kind = 'reported'
    operator = bool(re.search(r'运营方|运营团队|SaaS运营|该产品|该SaaS', quote, re.I))
    researcher = bool(re.search(r'(?:我|本人|个人|研究者|研究员)的?(?:个人)?研究|研究(?:者|员)(?:本人|个人)?(?:的|一人|投入|预算)|研究的?(?:预算|投入|现金|费用|成本|损失)|本轮个人', quote))
    subject = 'mixed' if operator and researcher else 'operator' if operator else 'researcher' if researcher else 'project'
    return {'knowledge': kind, 'subject': subject}


def complete_quote(quote, sources):
    """Recover the sentence around a clipped quote before checking its subject."""
    if not quote:
        return quote
    for text in reversed(sources):
        start = text.find(quote)
        if start < 0:
            continue
        end = start + len(quote)
        left = max((m.end() for m in re.finditer(r'[。；\n]', text[:start])), default=0)
        if text[end - 1] in '。；\n':
            return text[left:end].strip()
        right = re.search(r'[。；\n]', text[end:])
        return text[left:end + right.start() if right else len(text)].strip()
    return quote


def gap_details(project):
    """Build limitations from matched original quotes, never free-form model reasons."""
    sources = [project.get('description', '')] + [m.get('content', '') for m in project.get('messages', []) if m.get('role') == 'user']
    labels = {'not_obtained': '本次未取得相关资料，不能据此断定其不存在',
              'unknown': '用户尚不清楚，当前无法判断',
              'reported_absent': '用户作了否定表述，具体范围以原话为准',
              'unverified': '仍待核查或实际验证', 'reported': '仍有待核查的信息'}
    details = []
    for dim, entry in project.get('lifecycle', {}).get('coverage', {}).items():
        name = DIMENSIONS.get(dim, (dim,))[0]
        kinds, quotes = [], []
        for item in entry.get('items', {}).values():
            if item.get('status') not in ('unknown', 'external', 'future'):
                continue
            quote = item.get('quote', '').strip()
            if item.get('source') != 'user' or not item.get('verified') or not quote or not any(quote in s for s in sources):
                continue
            kind = qualification(quote, item['status'])['knowledge']
            if kind not in kinds:
                kinds.append(kind)
            if len(quote) <= 160:
                quotes.append(quote)
        if kinds:
            # Keep the report bounded; full quotes remain in checkpoint state and chat.
            line = name + '：' + '；'.join(labels[kind] for kind in kinds) + '。'
            if quotes:
                line += '用户原话示例：「' + quotes[0] + '」'
            details.append(line)
        elif entry.get('status') in ('unknown', 'external', 'future'):
            details.append(name + '：相关依据尚待补充或核查')
    return details


def unsupported_absence(text, limits, source_quotes=()):
    """A narrow guard for the missing-record/authorization errors seen in reports."""
    topics = (r'实测|测试|试点|记录', r'合规|授权|版权', r'案例|对照', '数据', '收入', '需求', '团队', '能力')
    for sentence in re.split(r'[。；\n]', text):
        if not re.search(r'不存在|(?:无|没有|缺乏|不具备)(?:任何|相关|可用|运营方的?)?(?:实测|测试|试点|记录|合规|授权|版权|案例|对照|数据|收入|需求|团队|能力)', sentence):
            continue
        if re.search(r'不能|无法|不足以|不代表|不等于|并非|尚未取得|未取得|未检索到|未拿到|未确认|不了解|不知道|未知|(?:如果|若).*(?:确认|核查)|用户(?:明确)?(?:表示|说)|用户原话|(?:目前|现有|本次)(?:的)?(?:资料|材料|信息)(?:中)?(?:没有|不含)', sentence):
            continue
        # A missing document does not negate a separate, explicit source statement.
        if any(sentence.strip() in quote and qualification(quote, 'known')['knowledge'] == 'reported_absent'
               for quote in source_quotes):
            continue
        for quote in limits:
            if any(re.search(topic, quote) and re.search(topic, sentence) for topic in topics):
                yield sentence.strip(), quote
                break
