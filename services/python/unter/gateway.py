import json
import os
import re
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

# Worker and agent routes are listed one by one. Every other /api path belongs to core, which
# authenticates and validates each request itself.
ROUTES = {
    'activity': ('WORKER_URL', 'http://worker:8000', '/activity', {'GET'}),
    'schedule': ('AGENT_URL', 'http://agent:8000', '/schedule', {'GET', 'PUT'}),
    'runs': ('AGENT_URL', 'http://agent:8000', '/runs', {'GET'}),
    'reports': ('AGENT_URL', 'http://agent:8000', '/reports', {'GET'}),
    'run': ('AGENT_URL', 'http://agent:8000', '/run', {'POST'}),
    'openapi': ('CORE_URL', 'http://core:8080', '/v3/api-docs', {'GET'}),
}
SEGMENT = re.compile(r'[A-Za-z0-9_-]+')
UUID_TEXT = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
MAX_REASON = 1000


def core_reason(proposal: dict, report_id: str) -> str:
    """The report's reason, with where it came from, within core's 1000-character limit."""
    suffix = f" (Unter report {report_id[:8]}, {proposal['id']})"
    return proposal['reason'][:MAX_REASON - len(suffix)] + suffix


def detail(response: httpx.Response, fallback: str) -> str:
    try:
        body = response.json()
        return str(body.get('detail') or body.get('message') or fallback)
    except ValueError:
        return fallback


@api.post('/reports/{report_id}/decisions')
async def decide(report_id: str, request: Request):
    """Approve or reject one proposal of a stored report, as the logged-in operator.

    The browser names the proposal; its zone and numbers come from the stored report via the agent,
    so they can't be changed on the way. Approving creates and approves the proposal in core with
    the gateway's login, which is what creates the surge rule or incentive. The agent never does.
    """
    if not UUID_TEXT.fullmatch(report_id):
        return JSONResponse({'detail': 'Not found'}, 404)
    raw = await request.body()
    if len(raw) > 16384:
        return JSONResponse({'detail': 'Request too large'}, 413)
    try:
        body = json.loads(raw)
        proposal_id, decision = body['proposal_id'], body['decision']
        assert isinstance(proposal_id, str) and decision in ('approved', 'rejected')
    except (ValueError, KeyError, TypeError, AssertionError):
        return JSONResponse({'detail': 'Send proposal_id and decision (approved or rejected)'}, 422)
    agent = os.getenv('AGENT_URL', 'http://agent:8000')
    core = os.getenv('CORE_URL', 'http://core:8080')
    headers = {'Authorization': basic_header()}
    key = {'report_id': report_id, 'proposal_id': proposal_id}
    try:
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            claim = await client.post(agent + '/decisions', json={**key, 'decision': decision})
            if claim.status_code != 200:
                return JSONResponse({'detail': detail(claim, 'Could not record the decision')}, claim.status_code)
            if decision == 'rejected':
                return JSONResponse({'status': 'rejected'})
            proposal = claim.json()['proposal']
            created = await client.post(core + '/proposals', json={
                'zone': proposal['zone'], 'type': proposal['type'], 'params': proposal['params'],
                'reason': core_reason(proposal, report_id)})
            if created.status_code not in (200, 201):
                await client.delete(agent + '/decisions', params=key)
                return JSONResponse({'detail': 'Core refused the proposal: ' + detail(created, 'unknown error')},
                                    created.status_code if created.status_code < 500 else 502)
            core_id = created.json()['id']
            approved = await client.patch(f'{core}/proposals/{core_id}', json={'status': 'approved'})
            status = 'applied' if approved.status_code == 200 else 'created'
            await client.put(agent + '/decisions', json={**key, 'status': status, 'core_proposal_id': core_id})
            if status == 'created':
                return JSONResponse({'detail': 'The proposal was created in core but not approved. '
                                               'Approve it under Proposals.', 'core_proposal_id': core_id}, 502)
            return JSONResponse({'status': 'applied', 'core_proposal_id': core_id})
    except httpx.HTTPError:
        return JSONResponse({'detail': 'Service temporarily unavailable'}, 503)


@api.api_route('/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH'])
async def forward(path: str, request: Request):
    segments = path.split('/')
    # Plain names and ids only: no '..', empty or encoded segments reach a backend.
    if not all(SEGMENT.fullmatch(segment) for segment in segments):
        return JSONResponse({'detail': 'Not found'}, 404)
    if segments[0] in ROUTES:
        env, default, target, methods = ROUTES[segments[0]]
        if len(segments) > 1 or request.method not in methods:
            return JSONResponse({'detail': 'Not found'}, 404)
        base = os.getenv(env, default)
    else:
        base, target = os.getenv('CORE_URL', 'http://core:8080'), '/' + path
    query = request.url.query
    url = base + target + ('?' + query if query else '')
    payload = await request.body()
    if len(payload) > 16384:
        return JSONResponse({'detail': 'Request too large'}, 413)
    try:
        async with httpx.AsyncClient(timeout=115) as client:
            response = await client.request(request.method, url,
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
                    'Authorization': basic_header('READER'),
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
