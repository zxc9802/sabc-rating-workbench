"""Authenticated, bounded Doubao streaming transcription; audio is never persisted."""
import asyncio
import gzip
import json
import os
import struct
import uuid
from contextlib import suppress

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool
from websockets.asyncio.client import connect
from sabc import auth

router = APIRouter()
ENDPOINT = 'wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async'


def packet(payload, *, audio=False, final=False):
    payload = gzip.compress(payload)
    return bytes([0x11, (0x20 if audio else 0x10) | (2 if final else 0), 0x01 if audio else 0x11, 0]) + struct.pack('>I', len(payload)) + payload


def response(data):
    if not isinstance(data, bytes) or len(data) < 8:
        raise ValueError('Invalid speech packet')
    kind, flags = data[1] >> 4, data[1] & 15
    offset = (data[0] & 15) * 4
    if kind == 15:
        raise ValueError('Speech provider rejected request')
    if kind != 9:
        return {}, False
    if flags & 1:
        offset += 4
    size = struct.unpack_from('>I', data, offset)[0]
    payload = data[offset + 4:]
    if len(payload) != size:
        raise ValueError('Truncated speech packet')
    if data[2] & 15 == 1:
        payload = gzip.decompress(payload)
    return json.loads(payload), bool(flags & 2)


@router.websocket('/api/speech/stream')
async def speech_stream(ws: WebSocket):
    origins = {os.getenv('SABC_UI_ORIGIN', '').rstrip('/'), 'http://localhost:3000', 'http://127.0.0.1:3000'} - {''}
    if ws.headers.get('origin') not in origins:
        await ws.close(code=4403)
        return
    try:
        authenticated = await run_in_threadpool(auth.authenticated, ws)
    except Exception:
        authenticated = False
    if not authenticated:
        await ws.close(code=4401)
        return
    await ws.accept()
    key = os.getenv('SABC_SPEECH_API_KEY', '')
    if not key:
        await ws.send_json({'error': '语音服务尚未配置，请先使用文字输入。'})
        await ws.close()
        return
    tasks = []
    try:
        async with asyncio.timeout(135):
            async with connect(ENDPOINT, additional_headers={
                'X-Api-Key': key,
                'X-Api-Resource-Id': os.getenv('SABC_SPEECH_RESOURCE_ID', 'volc.seedasr.sauc.duration'),
                'X-Api-Connect-Id': str(uuid.uuid4()),
            }, open_timeout=10, close_timeout=2, max_size=2**20) as upstream:
                await upstream.send(packet(json.dumps({
                    'user': {'uid': str(uuid.uuid4())},
                    'audio': {'format': 'pcm', 'codec': 'raw', 'rate': 16000, 'bits': 16, 'channel': 1},
                    'request': {'model_name': 'bigmodel', 'enable_itn': True, 'enable_punc': True, 'result_type': 'full'},
                }).encode()))
                stopped = asyncio.Event()

                async def upload():
                    total = 0
                    while True:
                        event = await asyncio.wait_for(ws.receive(), 15)
                        if event['type'] == 'websocket.disconnect':
                            raise WebSocketDisconnect()
                        chunk = event.get('bytes')
                        if chunk is not None:
                            total += len(chunk)
                            if len(chunk) > 64000 or len(chunk) % 2 or total > 120 * 32000:
                                raise ValueError('Audio limit exceeded')
                            await upstream.send(packet(chunk, audio=True))
                        elif event.get('text') == 'stop':
                            await upstream.send(packet(b'', audio=True, final=True))
                            stopped.set()
                            return
                        else:
                            raise ValueError('Invalid audio message')

                async def download():
                    async for data in upstream:
                        result, final = response(data)
                        text = result.get('result', {}).get('text')
                        if text is not None:
                            await ws.send_json({'text': text, 'final': final})
                        if final:
                            await ws.send_json({'done': True})
                            return
                    raise ValueError('Speech stream ended early')

                async def finish_timeout():
                    await stopped.wait()
                    await asyncio.sleep(10)
                    raise TimeoutError('Final transcript timed out')

                await ws.send_json({'ready': True})
                tasks = [asyncio.create_task(upload()), asyncio.create_task(download()), asyncio.create_task(finish_timeout())]
                # Upload finishes on stop; recognition remains alive for the final correction.
                while tasks:
                    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                    if tasks[1] in done:
                        break
                    await asyncio.wait_for(tasks[1], 10)
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        with suppress(Exception):
            await ws.send_json({'error': '语音识别连接中断或服务不可用，已识别文字保留，请重试。'})
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        with suppress(Exception):
            await ws.close()
