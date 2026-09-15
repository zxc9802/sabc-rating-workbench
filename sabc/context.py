"""Bounded model context; confirmed facts and pending changes remain separate."""
from sabc.rating import PROJECT_FIELDS


def model_context(project, company, evidence, messages):
    fields=set(PROJECT_FIELDS)|{'id','description','budget_requested','version','framing','data_period','decision_facts','report_revision'}
    clean={k:v for k,v in project.items() if k in fields}
    clean['pending_patch']=dict(project.get('pending_patch',{}))
    # Prior questions are already in conversation, not instructions for this turn.
    clean['interview']={k:v for k,v in project.get('interview',{}).items() if k != 'questions'}
    report_requested = project.get('_report_requested', False)
    if not report_requested:
        from sabc.lifecycle import context
        clean['lifecycle']=context(project)
    previous = project.get('_previous_stage_report')
    if previous:
        if report_requested:
            result = previous.get('result', {})
            clean['previous_stage_report'] = {
                'id': previous.get('id'), 'created_at': previous.get('created_at'),
                'missing': result.get('missing', []),
                'note': '历史报告仍保留供用户比较；旧等级和分数不作为本次评分先验。根据本次用户事实、证据和评分锚点独立计算，不沿用旧报告的公式或验证任务。',
            }
        else:
            clean['previous_stage_report']=previous
    # Never include project.messages/proposal: history has one bounded location.
    recent=messages[-16:]
    truncated = False
    if report_requested:
        # Report generation needs early corrections even after a long interview.
        # Assistant drafts and old conclusions must not outweigh the user's words.
        # Collection summaries and earlier report conclusions are model-derived,
        # not additional user evidence for a fresh score.
        clean.pop('lifecycle', None)
        recent = []
        remaining = 24000
        for index, message in reversed(list(enumerate(messages))):
            if message.get('role') != 'user':
                continue
            content = str(message.get('content', ''))
            if remaining <= 0:
                break
            truncated |= len(content) > remaining
            recent.append({'role': 'user', 'content': content[-remaining:], 'source_id': f'turn-{index}'})
            remaining -= len(recent[-1]['content'])
        recent.reverse()
        # With complete user history available, a model risk summary adds no
        # source evidence and can reintroduce gaps the user already corrected.
        # Preserve directly edited/legacy fields and summaries when history is truncated.
        if not truncated and len(recent) == sum(m.get('role') == 'user' for m in messages) and recent:
            if project.get('risks_source') == 'model' or 'risks' in clean['pending_patch']:
                clean.pop('risks', None)
            clean['pending_patch'].pop('risks', None)
    superseded={e.get('supersedes') for e in evidence if e.get('supersedes')}
    usable=[e for e in evidence if e.get('id') not in superseded]
    selected=[]
    for e in usable[:12]:
        item={k:v for k,v in e.items() if k not in ('content','images','frames')}
        content=str(e.get('content',''))
        item['content']=content[:6000]
        item['context_truncated']=len(content)>6000
        selected.append(item)
    return {'project':clean,'company':company,'evidence':selected,'conversation':recent,
            'context_limits':{'older_messages_omitted':max(0,len(messages)-len(recent)),
                              'conversation_chars_truncated': truncated,
                              'evidence_omitted':len(usable)-len(selected),
                              'note':'未包含的原始记录仍保留在项目中；截取内容不代表全文。'}}
