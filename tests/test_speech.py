import gzip
import json
import struct
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from sabc import speech


def server_packet(text, final=False):
    body = gzip.compress(json.dumps({'result': {'text': text}}).encode())
    return bytes([0x11, 0x93 if final else 0x91, 0x11, 0]) + struct.pack('>iI', -1 if final else 1, len(body)) + body


def test_protocol():
    assert speech.response(server_packet('你好')) == ({'result': {'text': '你好'}}, False)
    assert speech.response(server_packet('你好。', True))[1] is True
    with pytest.raises(ValueError):
        speech.response(server_packet('test')[:-1])
    with pytest.raises(ValueError):
        speech.response(bytes([0x11, 0xf0, 0x10, 0]) + b'\0' * 8)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('SABC_UI_ORIGIN', 'https://example.test')
    monkeypatch.setattr(speech.auth, 'authenticated', lambda ws: True)
    app = FastAPI()
    app.include_router(speech.router)
    return TestClient(app)


def test_requires_origin_and_login(client, monkeypatch):
    for origin in ('https://attacker.test', ''):
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect('/api/speech/stream', headers={'origin': origin}):
                pass
        assert error.value.code == 4403
    monkeypatch.setattr(speech.auth, 'authenticated', lambda ws: False)
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect('/api/speech/stream', headers={'origin': 'https://example.test'}):
            pass
    assert error.value.code == 4401


def test_missing_key(client, monkeypatch):
    monkeypatch.delenv('SABC_SPEECH_API_KEY', raising=False)
    with client.websocket_connect('/api/speech/stream', headers={'origin': 'https://example.test'}) as ws:
        assert '尚未配置' in ws.receive_json()['error']


def test_stream_and_stop(client, monkeypatch):
    import asyncio
    class Upstream:
        def __init__(self):
            self.queue = asyncio.Queue()
            self.frames = []
        async def send(self, data):
            self.frames.append(data)
            if data[1] == 0x20:
                await self.queue.put(server_packet('你好'))
            elif data[1] == 0x22:
                await self.queue.put(server_packet('你好。', True))
        def __aiter__(self): return self
        async def __anext__(self): return await self.queue.get()
    upstream = Upstream()
    @asynccontextmanager
    async def connect(*args, **kwargs):
        assert kwargs['additional_headers']['X-Api-Key'] == 'test-secret'
        yield upstream
    monkeypatch.setenv('SABC_SPEECH_API_KEY', 'test-secret')
    monkeypatch.setattr(speech, 'connect', connect)
    with client.websocket_connect('/api/speech/stream', headers={'origin': 'https://example.test'}) as ws:
        assert ws.receive_json() == {'ready': True}
        ws.send_bytes(b'\0' * 6400)
        assert ws.receive_json() == {'text': '你好', 'final': False}
        ws.send_text('stop')
        assert ws.receive_json() == {'text': '你好。', 'final': True}
        assert ws.receive_json() == {'done': True}
    initial = json.loads(gzip.decompress(upstream.frames[0][8:]))
    assert initial['audio']['rate'] == 16000
    assert initial['request']['result_type'] == 'full'
