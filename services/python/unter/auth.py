import base64
import hmac
import os
from starlette.responses import JSONResponse


def basic_header(kind='SERVICE'):
    raw = f"{os.environ[kind + '_USERNAME']}:{os.environ[kind + '_PASSWORD']}"
    return 'Basic ' + base64.b64encode(raw.encode()).decode()


class BasicAuth:
    """Authenticate at each exposed listener; health carries no application data."""
    def __init__(self, app, kind='SERVICE', csrf=False):
        self.app, self.kind, self.csrf = app, kind, csrf
        # Fail closed at startup instead of silently permitting empty credentials.
        for suffix in ('_USERNAME', '_PASSWORD'):
            if not os.environ.get(kind + suffix):
                raise RuntimeError('Missing authentication configuration')

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = {k.lower(): v for k, v in scope['headers']}
        if scope['path'] == '/healthz' and scope['method'] == 'GET':
            return await self.app(scope, receive, send)
        supplied = headers.get(b'authorization', b'')
        expected = basic_header(self.kind).encode()
        if not hmac.compare_digest(supplied, expected):
            response = JSONResponse({'detail': 'Authentication required'}, 401,
                                    headers={'WWW-Authenticate': 'Basic realm="Unter", charset="UTF-8"',
                                             'Cache-Control': 'no-store'})
            return await response(scope, receive, send)
        if self.csrf and scope['method'] not in ('GET', 'HEAD', 'OPTIONS'):
            # A foreign page cannot set this header without a CORS preflight.
            if headers.get(b'x-unter-request') != b'1':
                return await JSONResponse({'detail': 'Missing request header'}, 403)(scope, receive, send)
        async def secured_send(message):
            if message['type'] == 'http.response.start':
                message.setdefault('headers', []).extend([
                    (b'cache-control', b'no-store'),
                    (b'x-content-type-options', b'nosniff'),
                    (b'x-frame-options', b'DENY'),
                    (b'referrer-policy', b'same-origin'),
                ])
            await send(message)
        return await self.app(scope, receive, secured_send)
