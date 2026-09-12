"""Parse model output and retain safe diagnostics for bounded format retries."""
import json
import re

from pydantic import ValidationError


class ModelResponseError(ValueError):
    def __init__(self, message, stage, **details):
        super().__init__(message)
        self.stage = stage
        self.details = details
        self.retry_messages = []


def decode_json(text, stage):
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ModelResponseError('模型返回的 JSON 格式无效，请重试。', stage,
                                 error_code='invalid_json', position=error.pos,
                                 line=error.lineno, column=error.colno,
                                 output_chars=len(text)) from error


def parse_object(content):
    if not isinstance(content, str):
        raise ModelResponseError('模型没有返回文本内容。', 'response_json', error_code='missing_content')
    text = content.strip().lstrip('\ufeff').strip()
    fence = re.fullmatch(r'```(?:json)?\s*\n([\s\S]*?)\n?```', text, re.IGNORECASE)
    if fence:
        text = fence[1].strip()
    result = decode_json(text, 'response_json')
    if not isinstance(result, dict):
        raise ModelResponseError('模型必须返回一个 JSON 对象。', 'response_schema', error_code='object_required')
    return result


def format_failure(error, content):
    if isinstance(error, ModelResponseError):
        failure = error
    elif isinstance(error, ValidationError):
        errors = error.errors(include_input=False, include_context=False, include_url=False)
        failure = ModelResponseError('模型返回字段未通过校验。', 'response_schema',
                                     error_code='invalid_fields', error_count=len(errors),
                                     error_types=sorted({item['type'] for item in errors}),
                                     error_fields=['.'.join(map(str, item['loc']))[:160] for item in errors[:8]])
    else:
        failure = ModelResponseError(str(error), 'response_validation', error_code='invalid_analysis')
    # Raw output is transient retry context only. Audit records use details, never this text.
    correction = str(failure) + ' ' + json.dumps(failure.details, ensure_ascii=False)
    if isinstance(error, ValidationError):
        correction += ' 字段位置：' + ', '.join('.'.join(map(str, item['loc'])) for item in errors[:8])
    failure.retry_messages = ([{'role': 'assistant', 'content': content}] if isinstance(content, str) else []) + [
        {'role': 'user', 'content': '格式补正（内部校验，不是用户新问题）：' + correction +
         '\n仅修复上述格式或字段错误，返回完整 JSON 对象，不加代码块或解释文字。'
         '保留原用户问题、已知事实和待追问缺口，不因格式修复结束访谈，不向用户讲述修复过程。'
         '字段严格遵循系统约定，不新增字段，不擅自更改事实、评分、证据或验证阈值。'}]
    return failure
