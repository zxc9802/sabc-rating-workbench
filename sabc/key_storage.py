"""Windows per-user encryption; API keys never returned by the API."""
import base64
import ctypes
import os
from ctypes import wintypes
from urllib.parse import urlsplit


class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_byte))]


def transform(value,encrypt):
    if os.name!='nt': raise ValueError('当前系统请通过 SABC_API_KEY 环境变量提供密钥')
    buffer=ctypes.create_string_buffer(value)
    source=Blob(len(value),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_byte)))
    target=Blob()
    crypt=ctypes.windll.crypt32
    fn=crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    if not fn(ctypes.byref(source),None,None,None,None,0,ctypes.byref(target)):
        raise ValueError('本机密钥加密存储失败')
    try: return ctypes.string_at(target.data,target.size)
    finally: ctypes.windll.kernel32.LocalFree(target.data)


def encrypt_key(value):
    return base64.b64encode(transform(value.encode(),True)).decode()


def decrypt_key(value):
    return transform(base64.b64decode(value),False).decode() if value else os.getenv('SABC_API_KEY','')


def key_origin(base):
    parsed = urlsplit(base)
    return (parsed.scheme.lower(), parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))


def model_key(settings):
    if settings.get('key_disabled'):
        return ''
    if settings.get('encrypted_key'):
        return decrypt_key(settings['encrypted_key'])
    key = os.getenv('SABC_API_KEY', '')
    if key and key_origin(settings.get('base_url', '')) != key_origin(os.getenv('SABC_MODEL_BASE_URL', '')):
        raise ValueError('模型地址已改变，请为新服务配置对应密钥，或明确清除原密钥')
    return key
