from fastmcp import FastMCP
from starlette.responses import JSONResponse
from .auth import BasicAuth
from .common import core

mcp = FastMCP('Unter example data')


@mcp.tool()
async def list_observations() -> list[dict]:
    """Read all seeded example zone observations from the Java API and PostgreSQL."""
    return await core('GET', '/observations')


@mcp.tool()
async def list_pending_proposals() -> list[dict]:
    """List pending demonstration proposals; the hello-world agent does not create these."""
    return [row for row in await core('GET', '/proposals') if row['status'] == 'pending']


@mcp.tool()
async def create_proposal(zone: str, reason: str) -> dict:
    """Propose a demonstration change for human approval, without applying real actions."""
    return await core('POST', '/proposals', json={'zone': zone, 'reason': reason})


@mcp.custom_route('/healthz', methods=['GET'])
async def health(request):
    return JSONResponse({'status': 'ok'})

app = mcp.http_app(path='/mcp', stateless_http=True)
app.add_middleware(BasicAuth)
