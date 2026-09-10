"""Bounded model context; confirmed facts and pending changes remain separate."""
from sabc.rating import PROJECT_FIELDS


def model_context(project, company, evidence, messages):
    fields=set(PROJECT_FIELDS)|{'id','description','budget_requested','version'}
    clean={k:v for k,v in project.items() if k in fields}
    clean['pending_patch']=project.get('pending_patch',{})
    clean['interview']=project.get('interview',{})
    # Never include project.messages/proposal: history has one bounded location.
    recent=messages[-16:]
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
                              'evidence_omitted':len(usable)-len(selected),
                              'note':'未包含的原始记录仍保留在项目中；截取内容不代表全文。'}}
