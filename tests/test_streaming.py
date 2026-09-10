import json
import httpx
from sabc.streaming import completion, progress, reply_prefix


def test_partial_json_escapes_and_structured_fields_are_not_shown():
    text='预算8000元\n引用"原文"\\路径😀'
    raw=json.dumps({'reply':text,'proposal':{'secret':'not visible'}},ensure_ascii=True)
    for i in range(1,len(raw)):
        value=reply_prefix(raw[:i])
        assert 'proposal' not in value and 'secret' not in value
    assert reply_prefix(raw)==text
    assert reply_prefix('{"proposal":null}')==''


def test_actual_stream_deltas_form_final_json():
    raw='{"reply":"逐步输出","proposal":null}'
    events=''.join('data: '+json.dumps({'choices':[{'delta':{'content':x}}]},ensure_ascii=False)+'\n\n' for x in raw)+'data: [DONE]\n\n'
    def transport(request):
        assert json.loads(request.content)['stream'] is True
        return httpx.Response(200,text=events,headers={'content-type':'text/event-stream'})
    seen=[];token=progress.set(seen.append)
    try:
        with httpx.Client(transport=httpx.MockTransport(transport)) as client:
            result=completion(client,'https://model.test/v1/chat/completions',{}, {},30)
    finally:progress.reset(token)
    assert result==raw and seen[-1]=='逐步输出'
    assert '逐' in seen


def test_truncated_stream_is_not_accepted_as_success():
    import pytest
    raw='{"reply":"看似完整","proposal":null}'
    events='data: '+json.dumps({'choices':[{'delta':{'content':raw}}]})+'\n\n'
    token=progress.set(lambda value:None)
    try:
        with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,text=events))) as client:
            with pytest.raises(ValueError,match='中断'):
                completion(client,'https://model.test/v1/chat/completions',{}, {},30)
    finally:progress.reset(token)
