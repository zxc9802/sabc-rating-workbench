"""Bounded model context; confirmed facts and pending changes remain separate."""
from sabc.rating import PROJECT_FIELDS


def model_context(project, company, evidence, messages):
    fields=set(PROJECT_FIELDS)|{'id','description','budget_requested','version'}
    clean={k:v for k,v in project.items() if k in fields}
    clean['pending_patch']=project.get('pending_patch',{})
    clean['interview']=project.get('interview',{})
    from sabc.lifecycle import context
    clean['lifecycle']=context(project)
    report_requested = project.get('_report_requested', False)
    previous = project.get('_previous_stage_report')
    if previous:
        if report_requested:
            result = previous.get('result', {})
            clean['previous_stage_report'] = {
                'id': previous.get('id'), 'created_at': previous.get('created_at'),
                'grade': result.get('grade'), 'base_score': result.get('base_score'),
                'missing': result.get('missing', []),
                'dimensions': [{k: d.get(k) for k in ('key', 'score', 'basis')}
                               for d in result.get('dimensions', [])],
                'note': '仅供比较的历史评级；不是事实依据。重新根据用户原话计算，不沿用旧报告的公式或验证任务。',
            }
        else:
            clean['previous_stage_report']=previous
    # Never include project.messages/proposal: history has one bounded location.
    recent=messages[-16:]
    truncated = False
    if report_requested:
        # Report generation needs early corrections even after a long interview.
        # Assistant drafts and old conclusions must not outweigh the user's words.
        clean['lifecycle'].pop('review', None)
        clean['lifecycle'].pop('recent_reviews', None)
        recent = []
        remaining = 24000
        for message in reversed(messages):
            if message.get('role') != 'user':
                continue
            content = str(message.get('content', ''))
            if remaining <= 0:
                break
            truncated |= len(content) > remaining
            recent.append({'role': 'user', 'content': content[-remaining:]})
            remaining -= len(recent[-1]['content'])
        recent.reverse()
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
