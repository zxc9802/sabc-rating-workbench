"""Stream visible reply text while the final structured result remains uncommitted."""
from contextvars import ContextVar
import json
import re
import time
from sabc.model_output import ModelResponseError, decode_json

progress = ContextVar('model_progress', default=None)
cancel_signal = ContextVar('model_cancel_signal', default=None)


class JobCancelled(BaseException):
    pass


def check_cancelled():
    signal = cancel_signal.get()
    if signal is not None and signal.is_set():
        raise JobCancelled()


def reply_prefix(content):
    match = re.search(r'"reply"\s*:\s*"', content)
    if not match:
        return ''
    value = content[match.end():]
    end = 0
    while end < len(value):
        if value[end] == '"':
            break
        if value[end] == '\\':
            size = 6 if value[end:end+2] == '\\u' else 2
            if end + size > len(value):
                break
            end += size
        else:
            end += 1
    try:
        decoded = json.loads('"' + value[:end] + '"')
        return decoded.encode('utf-8', errors='ignore').decode('utf-8')
    except ValueError:
        return ''


def completion(client, url, payload, headers, remaining):
    check_cancelled()
    if url.endswith(':generateContent'):
        return gemini_completion(client, url, payload, headers, remaining)
    notify = progress.get()
    if notify is None and not payload.get('stream'):
        r = client.post(url, json=payload, headers=headers, timeout=remaining)
        r.raise_for_status()
        check_cancelled()
        choice = decode_json(r.text, 'transport_json')['choices'][0]
        if choice.get('finish_reason') not in (None, 'stop'):
            raise ModelResponseError('模型未完成有效回答', 'response_incomplete', error_code='unfinished_output')
        return choice['message']['content']
    notify = notify or (lambda _: None)
    notify('')
    content = ''
    finished = False
    deadline = time.monotonic() + remaining
    with client.stream('POST', url, json={**payload, 'stream':True}, headers=headers, timeout=remaining) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            check_cancelled()
            if time.monotonic() > deadline:
                raise ModelResponseError('模型回答超时，请重试', 'timeout', error_code='stream_deadline')
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                finished = True
                break
            if not data:
                continue
            event = decode_json(data, 'stream_json')
            if event.get('error'):
                raise ModelResponseError('模型流式回答中断，请重试', 'stream_transport', error_code='upstream_error')
            choices = event.get('choices', [])
            if choices:
                reason = choices[0].get('finish_reason')
                if reason not in (None, 'stop'):
                    raise ModelResponseError('模型未完成有效回答', 'response_incomplete', error_code='unfinished_output')
                if reason == 'stop':
                    finished = True
                delta = choices[0].get('delta', {}).get('content')
                if isinstance(delta, str):
                    content += delta
                    notify(reply_prefix(content))
    if not finished:
        raise ModelResponseError('模型流式回答中断，请重试', 'stream_transport', error_code='missing_finish')
    return content


def gemini_completion(client, url, payload, headers, remaining):
    messages = payload['messages']
    body = {'contents': [
        {'role': 'model' if message['role'] == 'assistant' else 'user',
         'parts': [{'text': message['content']}]} for message in messages if message['role'] != 'system'],
        'systemInstruction': {'parts': [{'text': '\n'.join(
            message['content'] for message in messages if message['role'] == 'system')}]},
        'generationConfig': {'responseMimeType': 'application/json'}}
    for source, target in (('temperature', 'temperature'), ('max_tokens', 'maxOutputTokens')):
        if source in payload:
            body['generationConfig'][target] = payload[source]
    response = client.post(url, json=body, headers=headers, timeout=remaining)
    response.raise_for_status()
    check_cancelled()
    candidates = decode_json(response.text, 'transport_json').get('candidates') or []
    if not candidates or candidates[0].get('finishReason') != 'STOP':
        raise ModelResponseError('模型未完成有效回答', 'response_incomplete', error_code='unfinished_output')
    content = ''.join(part.get('text', '') for part in candidates[0].get('content', {}).get('parts', [])
                      if not part.get('thought'))
    if not content.strip():
        raise ModelResponseError('模型未返回有效正文', 'response_incomplete', error_code='empty_output')
    # Publish only after the caller validates the structured response; failed attempts stay invisible.
    return content
