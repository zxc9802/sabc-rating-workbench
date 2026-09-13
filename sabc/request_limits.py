"""Bound request bodies before multipart parsing or temporary-file writes."""
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

MAX_BODY_BYTES = 20_000_000 + 65_536  # One 20 MB file plus multipart headers.


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        length = dict(scope.get('headers', [])).get(b'content-length', b'')
        if length.isdigit() and int(length) > MAX_BODY_BYTES:
            return await JSONResponse({'detail': '请求内容过大，单个文件最大20MB'}, status_code=413)(scope, receive, send)
        total = 0
        async def limited_receive():
            nonlocal total
            message = await receive()
            total += len(message.get('body', b''))
            if total > MAX_BODY_BYTES:
                raise HTTPException(413, '请求内容过大，单个文件最大20MB')
            return message
        await self.app(scope, limited_receive, send)
