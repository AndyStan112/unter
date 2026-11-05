from typing import Annotated, Literal
import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field
from starlette.responses import JSONResponse
from .analytics import stats
from .auth import BasicAuth
from .common import core_read

# Read-only by design: every tool only reads core, with a login core refuses for writes.
# Adding a tool? Add it to READ_ONLY_TOOLS in tests/test_mcp_read_only.py after checking it only reads.
# Tools take a zone, a time window and a bucket, never SQL, and return aggregates, never trip or rider rows.
mcp = FastMCP('Unter zone analytics', instructions=(
    'Read-only metrics about Unter trips, offers and drivers per zone, for proposing surge rates and driver '
    'incentives. Start with zone_snapshot; use the other tools to look closer. Times are ISO-8601 with an '
    'offset (e.g. 2026-11-03T08:00:00Z); without start/end a tool covers the last 24 hours.'))

Start = Annotated[str | None, Field(description='Window start, ISO-8601 with offset. Default: 24 hours before end.')]
End = Annotated[str | None, Field(description='Window end (exclusive), ISO-8601 with offset. Default: now.')]
Zone = Annotated[str | None, Field(description='Only this zone (see list_zones). Default: all zones.')]
Bucket = Annotated[Literal['15m', '1h', '6h', '1d'], Field(description='Time bucket size, aligned to UTC.')]


async def read(path: str, params: dict | None = None):
    try:
        return await core_read(path, params)
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 400:
            raise ToolError(f'core refused the request: {error.response.text[:300]}') from None
        raise


async def known_zone(zone: str | None) -> str | None:
    return None if zone is None else stats.check_zone(zone, await read('/zones'))


@mcp.tool()
async def list_zones() -> list[dict]:
    """The zones Unter divides the city into, with their centers. Trips belong to their pickup zone."""
    return [{'name': z['name'], 'lat': z['lat'], 'lon': z['lon']} for z in await read('/zones')]


@mcp.tool()
async def zone_demand(start: Start = None, end: End = None, bucket: Bucket = '1h', zone: Zone = None) -> dict:
    """Trip metrics per pickup zone and time bucket: requests, completed, cancelled, unmatched, open,
    unmatched/cancel rates, average and p90 wait for a driver (seconds), average completed price,
    arrivals (completed trips dropping off in the zone) and net_flow = arrivals - completed
    (completed trips in minus completed trips out; negative: the zone drains drivers)."""
    win = stats.window(start, end)
    query = {**win.params(), 'bucket': stats.check_bucket(bucket, win)}
    if zone := await known_zone(zone):
        query['zone'] = zone
    result = await read('/stats/zones', query)
    return {'from': result['from'], 'to': result['to'], 'bucket': result['bucket'], 'note': stats.EMPTY_NOTE,
            'rows': stats.demand_rows(result['rows'])}


@mcp.tool()
async def zone_flows(start: Start = None, end: End = None, zone: Zone = None) -> dict:
    """Trips from pickup zone (origin) to dropoff zone (destination) over the window, with how many
    completed. With a zone, only pairs where it is the origin or the destination."""
    win = stats.window(start, end)
    zone = await known_zone(zone)
    result = await read('/stats/flows', win.params())
    return {'from': result['from'], 'to': result['to'], 'note': 'Pairs left out had no trips.',
            'flows': stats.flow_rows(result['flows'], zone)}


@mcp.tool()
async def offer_stats(start: Start = None, end: End = None, bucket: Bucket = '1h', zone: Zone = None) -> dict:
    """How drivers respond to trips offered in each pickup zone, per time bucket: offers, accepted,
    rejected, expired, distinct drivers offered, reject/expiry rates and offers per requested trip.
    High reject or expiry rates mean drivers avoid the zone."""
    win = stats.window(start, end)
    query = {**win.params(), 'bucket': stats.check_bucket(bucket, win)}
    if zone := await known_zone(zone):
        query['zone'] = zone
    result = await read('/stats/zones', query)
    return {'from': result['from'], 'to': result['to'], 'bucket': result['bucket'],
            'note': 'Buckets left out had no offers.', 'rows': stats.offer_rows(result['rows'])}


@mcp.tool()
async def driver_supply(zone: Zone = None) -> dict:
    """Drivers per zone right now (history isn't stored): available (usable by dispatch), offered,
    on_trip, stale (available but no recent position), and waiting_trips still looking for a driver."""
    zone = await known_zone(zone)
    result = await read('/stats/supply')
    return {'as_of': result['as_of'], 'zones': [z for z in result['zones'] if zone in (None, z['zone'])]}


@mcp.tool()
async def active_rules() -> dict:
    """Surge multipliers and driver incentives in effect right now, per zone (null when none)."""
    zones, surge, incentives = await read('/zones'), await read('/surge'), await read('/incentives')
    surge, incentives = stats.by_zone(surge), stats.by_zone(incentives)
    return {z['name']: {'surge': stats.rule_view(surge.get(z['name'])),
                        'incentive': stats.rule_view(incentives.get(z['name']))} for z in zones}


@mcp.tool()
async def zone_snapshot(start: Start = None, end: End = None) -> dict:
    """The main analysis tool: one summary per zone over the window. Totals and rates, wait times,
    net_flow, requests_per_hour, offer reject/expiry rates, the busiest hour (peak_bucket), drivers
    available now (supply_now), demand_supply_ratio = requests_per_hour / max(available drivers, 1),
    and the surge and incentive active now."""
    win = stats.window(start, end)
    query = {**win.params(), 'bucket': '1h'}
    zones, demand = await read('/zones'), await read('/stats/zones', query)
    supply = stats.by_zone((await read('/stats/supply'))['zones'])
    surge, incentives = stats.by_zone(await read('/surge')), stats.by_zone(await read('/incentives'))
    return {'from': demand['from'], 'to': demand['to'], 'hours': round(win.hours, 2),
            'zones': [stats.zone_summary(z['name'], demand['rows'], supply.get(z['name']), surge.get(z['name']),
                                         incentives.get(z['name']), win.hours) for z in zones]}


@mcp.custom_route('/healthz', methods=['GET'])
async def health(request):
    return JSONResponse({'status': 'ok'})

app = mcp.http_app(path='/mcp', stateless_http=True)
# Callers (agent, gateway) authenticate with the READER login too; the MCP pod holds no other.
app.add_middleware(BasicAuth, kind='READER')
