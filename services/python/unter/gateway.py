import os
from pathlib import Path
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from .auth import BasicAuth, basic_header

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
# The static shell contains no private data and can be installed/offline cached.
# All application data and actions require this one administrator login.


@app.get('/healthz')
def health():
    return {'status': 'ok'}

api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
api.add_middleware(BasicAuth, kind='ADMIN', csrf=True)

ROUTES = {
    'observations': ('CORE_URL', 'http://core:8080', '/observations', {'GET'}),
    'proposals': ('CORE_URL', 'http://core:8080', '/proposals', {'GET', 'POST', 'PATCH'}),
    'activity': ('WORKER_URL', 'http://worker:8000', '/activity', {'GET'}),
    'schedule': ('AGENT_URL', 'http://agent:8000', '/schedule', {'GET', 'PUT'}),
    'runs': ('AGENT_URL', 'http://agent:8000', '/runs', {'GET'}),
    'run': ('AGENT_URL', 'http://agent:8000', '/run', {'POST'}),
    'openapi': ('CORE_URL', 'http://core:8080', '/v3/api-docs', {'GET'}),
}


@api.api_route('/{name}', methods=['GET', 'POST', 'PUT'])
@api.api_route('/{name}/{item}', methods=['PATCH'])
async def forward(name: str, request: Request, item: str | None = None):
    if name not in ROUTES or request.method not in ROUTES[name][3] or (item and name != 'proposals'):
        return JSONResponse({'detail': 'Not found'}, 404)
    env, default, path, _ = ROUTES[name]
    if item:
        import uuid
        try:
            path += '/' + str(uuid.UUID(item))
        except ValueError:
            return JSONResponse({'detail': 'Invalid identifier'}, 400)
    payload = await request.body()
    if len(payload) > 16384:
        return JSONResponse({'detail': 'Request too large'}, 413)
    try:
        async with httpx.AsyncClient(timeout=115) as client:
            response = await client.request(request.method, os.getenv(env, default) + path,
                content=payload, headers={'Authorization': basic_header(), 'Content-Type': 'application/json'})
        # Backend responses are controlled JSON; never forward service auth challenges.
        return Response(response.content, status_code=response.status_code, media_type='application/json')
    except httpx.HTTPError:
        return JSONResponse({'detail': 'Service temporarily unavailable'}, 503)

app.mount('/api', api)
# The MCP server independently authenticates, including direct internal requests.
# Proxy with the MCP SDK HTTP transport semantics (streamable HTTP, stateless).


@app.api_route('/mcp', methods=['GET', 'POST', 'DELETE'])
async def mcp_proxy(request: Request):
    import hmac
    if not hmac.compare_digest(request.headers.get('authorization', '').encode(), basic_header('ADMIN').encode()):
        return JSONResponse({'detail': 'Authentication required'}, 401,
                            headers={'WWW-Authenticate': 'Basic realm="Unter"'})
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(request.method, os.getenv('MCP_URL', 'http://mcp:8000/mcp'),
                content=await request.body(), headers={
                    'Authorization': basic_header(),
                    'Content-Type': request.headers.get('content-type', 'application/json'),
                    'Accept': request.headers.get('accept', 'application/json, text/event-stream'),
                    'MCP-Protocol-Version': request.headers.get('mcp-protocol-version', '2025-06-18'),
                })
        return Response(response.content, status_code=response.status_code,
                        headers={'content-type': response.headers.get('content-type', 'application/json'), 'cache-control': 'no-store'})
    except httpx.HTTPError:
        return JSONResponse({'detail': 'MCP unavailable'}, 503)

web = Path(os.getenv('WEB_ROOT', '/app/web'))
if not web.exists():
    web = Path(__file__).resolve().parents[3] / 'web'
app.mount('/', StaticFiles(directory=web, html=True), name='web')
