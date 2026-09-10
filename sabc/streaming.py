"""Stream visible reply text while the final structured result remains uncommitted."""
from contextvars import ContextVar
import json
import re
import time

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
    notify = progress.get()
    if notify is None:
        r = client.post(url, json=payload, headers=headers, timeout=remaining)
        r.raise_for_status()
        check_cancelled()
        choice = r.json()['choices'][0]
        if choice.get('finish_reason') not in (None, 'stop'):
            raise ValueError('模型未完成有效回答')
        return choice['message']['content']
    notify('')
    content = ''
    finished = False
    deadline = time.monotonic() + remaining
    with client.stream('POST', url, json={**payload, 'stream':True}, headers=headers, timeout=remaining) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            check_cancelled()
            if time.monotonic() > deadline:
                raise ValueError('模型回答超时，请重试')
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                finished = True
                break
            if not data:
                continue
            event = json.loads(data)
            if event.get('error'):
                raise ValueError('模型流式回答中断，请重试')
            choices = event.get('choices', [])
            if choices:
                reason = choices[0].get('finish_reason')
                if reason not in (None, 'stop'):
                    raise ValueError('模型未完成有效回答')
                if reason == 'stop':
                    finished = True
                delta = choices[0].get('delta', {}).get('content')
                if isinstance(delta, str):
                    content += delta
                    notify(reply_prefix(content))
    if not finished:
        raise ValueError('模型流式回答中断，请重试')
    return content
