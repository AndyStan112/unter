# Concurrent client simulator

The simulator makes real asynchronous HTTP requests through the authenticated gateway.
It creates its own named riders and drivers and drives the trip lifecycle through public
endpoints; it does not insert rows directly or call the paid report agent. Trips, offers,
zone transitions and activity events remain in the database, so the dashboard, stats,
MCP analytics and later scheduled reports have a growing history to inspect.

Run against an **isolated local or staging stack**. Startup refuses existing online
or busy drivers and open trips. Keep other clients off that stack during the run.
This prevents the simulator from responding to another client's offer and makes the
scarce-supply assertions meaningful. Existing historical data and offline drivers are fine.

```sh
AGENT_MODE=fake docker compose up -d --build
make simulate
# Ten-minute run, faster actors, different random choices:
make simulate SIM_ARGS='--duration 600 --riders 24 --drivers 6 --seed 73 --pace 0.5'
# Longer run, retaining real server timeout behavior:
make simulate SIM_ARGS='--duration 21600 --riders 40 --drivers 10 --snapshot-interval 60'
```

Alternatively use `uv run --project services/python python scripts/simulate.py ...`.
Credentials come from `ADMIN_USERNAME` / `ADMIN_PASSWORD` in the environment or root
`.env`. `--url` (or `UNTER_URL`) selects the gateway, defaulting to
`http://localhost:5180`. `--output` selects the evidence directory. Run `--help` for
all options. At least two riders and one driver are required.

## Traffic and targeted races

Before the timed random workload, three rounds (`--race-rounds`) run these scenarios:

| Scenario | Assertion |
| --- | --- |
| All riders book together with one available driver | Exactly one trip holds that driver |
| Eight simultaneous bookings by one rider | Exactly one booking succeeds |
| Eight simultaneous accepts of one offer | Exactly one succeeds; trip and driver agree |
| Accept versus rider cancellation | Final trip is cancelled and driver released |
| Accept versus going offline | Either accepted and on trip, or offline with offer released |

Each burst uses a start barrier and a connection pool large enough for concurrent
requests. The random phase has one task per rider and driver. Pickups cluster 80% of
the time around a hotspot that rotates among the configured zones. Alternating rush
and quiet periods change exponentially distributed interarrival times. Drivers send
location updates, accept or reject offers, sometimes leave an offer unanswered until
it expires, go offline briefly, pick up and complete trips. Riders have varying patience
and cancel if they wait too long. A fixed seed repeats random decisions per actor;
network ordering and server timing still vary. This is a synthetic workload, not a
calibrated forecast of an actual ride-hailing market.

`--duration` bounds the random phase; setup, targeted races and cleanup take extra time.
`--pace` scales client delays and hotspot/rush periods, leaving the server's offer,
matching and position-age timeouts intact. Use longer runs to observe expirations and
unmatched trips; the short CI run need not encounter every random outcome.

Only documented conflict codes for the specific operation count as expected race
losers. Unexpected responses, transport failures and failed assertions produce a nonzero
exit status. The simulator does not retry ambiguous writes, which could hide a bug.
At the end (also after a failure or Ctrl-C), it stops the actors, waits for in-flight
responses, cancels its open trips, completes picked-up trips and takes its drivers
offline. It checks every tracked trip is terminal and each driver has no current trip.
Cleanup failures remain failures. An interrupted connection can commit a write without
a response; use the actor IDs in the log to investigate those failures. A forced kill
cannot clean up, so do not reuse that stack until its open trips are resolved.

## Evidence over time

Each invocation writes a unique, flushed JSONL file under `.local/simulations/` (ignored
by git). It contains timestamps, configuration and seed, actor/trip IDs, scenario checks,
per-request operation/path/status/error code/latency, periodic `/stats/supply` and
`/stats/zones` snapshots, progress metrics and a final pass/fail summary with terminal trip counts. It contains
no credentials, request bodies, model responses or raw server error messages.

Counts, average requests per second and maximum observed concurrent requests are cumulative. p50, p95 and maximum
latencies are per operation over its most recent 10,000 requests, bounding measurement
memory during long runs. Full request samples remain in the JSONL for offline comparison.
Stats snapshots include all history in the endpoint's default window, not just this run;
use timestamps and actor/trip IDs when comparing runs. Actor and trip ownership is retained
in memory for cleanup, and evidence and database history grow with the run. Plan disk
retention for long soaks; nothing deletes that evidence or history automatically.

CI runs two targeted rounds and 30 seconds of random traffic against the full fake-agent
Compose stack, fails on invariant errors, and uploads JSONL evidence for 14 days even
when the simulator fails. It exercises concurrency without spending model tokens. Local
soak runs are opt-in and can generate data for hours without leaving a background writer
or changing the report schedule.
