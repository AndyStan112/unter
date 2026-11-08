import asyncio
import os
os.environ.setdefault('READER_USERNAME', 'test-reader')
os.environ.setdefault('READER_PASSWORD', 'test-reader-password')
import httpx
from fastmcp import Client
from unter import common, mcp_server
from unter.auth import basic_header

# Every tool here has been checked to only read. Review a new tool before adding it.
READ_ONLY_TOOLS = {'list_zones', 'zone_demand', 'zone_flows', 'offer_stats', 'driver_supply', 'active_rules',
                   'zone_snapshot'}


def test_mcp_exposes_only_reviewed_read_only_tools():
    async def names():
        async with Client(mcp_server.mcp) as client:
            return {tool.name for tool in await client.list_tools()}
    assert asyncio.run(names()) == READ_ONLY_TOOLS


def test_mcp_cannot_use_the_writing_core_client():
    assert not hasattr(mcp_server, 'core'), 'mcp_server must use core_read only'


def test_core_read_sends_only_get_with_the_reader_login(monkeypatch):
    seen = []
    def reply(request):
        seen.append(request)
        return httpx.Response(200, json=[])
    real = httpx.AsyncClient
    monkeypatch.setattr(common.httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(reply), **kw))
    assert asyncio.run(common.core_read('/proposals', {'limit': 5})) == []
    request, = seen
    assert request.method == 'GET' and request.url.path == '/proposals' and request.url.params['limit'] == '5'
    assert request.headers['authorization'] == basic_header('READER')
