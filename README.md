# Unter

A deliberately small distributed application: seeded PostgreSQL rows, a Java API,
RabbitMQ events, a Python worker and read-only MCP server, an Agno agent that proposes
surge rates and driver incentives in a report, and an
admin website and an installable passenger/driver PWA.

## Passenger and driver PWA

Open `/ride/` on the same origin as the gateway (locally, <http://localhost:5180/ride/>).
The responsive React / Material UI PWA has passenger and driver modes, with separate profiles
remembered in browser local storage. Use two browsers or devices to try both sides:
create a driver, choose a zone or enable live GPS, go online, then create a passenger
and request a trip. The driver can accept or decline, confirm pickup and complete;
the passenger can follow progress and cancel before pickup. Keep the driver app
open: it polls every 2.5 seconds and sends location roughly every 7.5 seconds.

This uses the current development API's shared Basic Auth, not private user accounts.
Profile IDs are browser-local identifiers, not authentication credentials. Real accounts
and role-based authorization require backend changes before public use. Pickup and destination can be searched by address, selected from zone centers or pinned on the
interactive Leaflet / OpenStreetMap map. Road routes show distance, estimated travel time and
step-by-step directions; drivers can open live navigation. Pickup ETAs use fresh driver positions.
Estimates exclude live traffic. When routing is unavailable, dashed straight-line connections
are labelled and ETA is unavailable. Static assets contain no credentials; requests use same-origin `/api/`
and the gateway's required mutation header.

## Mock earnings and payments

Drivers see an all-time mock balance, today's earnings (Europe/Bucharest), completed ride count,
fare/bonus totals and their last 50 settlements. Earnings are the full fare plus the newest
incentive active in the pickup zone at acceptance; the bonus is locked then and is not deducted
from the passenger fare. Completion settles both once in the same transaction, even if retried.
Cancellation and unmatched requests earn nothing. No real charges, withdrawals or transfers occur.
Passenger and driver history survives reloads; profiles still live in browser storage.
Existing completed rides are backfilled with their stored fare and zero historical bonus.

Report approval is atomic in core under a permanent `(report_id, proposal_id)` key. Replays return
the same proposal, including after expiration. The gateway reconciles interrupted approvals every
15 seconds; failures are visible with a retry action. Existing partial approvals are adopted when
unambiguous. The agent never calls core or applies its own proposals.

## Maps, location and notifications

`ROUTING_URL` selects an OSRM-compatible backend (default `https://router.project-osrm.org`);
`GEOCODING_URL` selects Photon (default `https://photon.komoot.io`). Address searches are explicit,
throttled and cached, biased towards Timișoara. Routes have bounded caches and timeouts; moving
driver routes refresh at most every 10 seconds. Public demo providers have no availability guarantee;
configure your own providers for significant traffic. Search/route coordinates go to those providers.
See [Photon](https://photon.komoot.io/) and [OSRM](https://project-osrm.org/docs/v5.24.0/api/).

Enable notifications separately for the profile receiving alerts on a device. Web Push delivers
ride offers and passenger status updates through the PWA service worker, including while the app
is closed. It requires HTTPS (or localhost), browser permission, and installation on iPhone.
The activity database persists the VAPID identity, subscriptions and deduplicated retry queue;
no third-party API key is needed. Keep that database backed up: replacing the identity requires
resubscribing devices. Invalid subscriptions are removed, expired offers are not displayed, and
notification payloads contain no credentials or detailed trip data. Delivery remains best-effort;
phone/browser policies can delay notifications.

Live GPS requires the app to remain active. Drivers can request screen wake lock; phones may still
suspend background GPS. Stale positions are shown and dispatch excludes drivers without a location
updated within two minutes. True continuous background tracking requires a native app.

## Start locally

Prerequisites: Docker Compose and [uv](https://docs.astral.sh/uv/).

```sh
test -f .env || cp .env.example .env
# Set OPENAI_API_KEY in your editor. Never commit .env.
UV_CACHE_DIR=/tmp/unter-uv-cache uv sync --project services/python --frozen
UV_CACHE_DIR=/tmp/unter-uv-cache uv run --project services/python python scripts/init-env.py
docker compose up -d --build
```

On Windows (PowerShell):

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Set OPENAI_API_KEY in your editor. Never commit .env.
$env:UV_CACHE_DIR = "$env:TEMP\unter-uv-cache"
uv sync --project services/python --frozen
uv run --project services/python python scripts/init-env.py
docker compose up -d --build
```

Open <http://localhost:5180> for the dashboard or <http://localhost:5180/ride/> for the PWA. The data requests ask for the `ADMIN_USERNAME` and
`ADMIN_PASSWORD` from `.env` once; the browser reuses Basic Auth on this origin.
Static web assets are public and contain no application data or credentials.
All data, administration and MCP access require authentication. Only `/ride/` is installable and caches its static shell. Ride actions require a
connection; last-known status is labelled offline. The dashboard has no manifest or
active service worker. Existing dashboard workers retire on the next online visit.

`.env` is the local source for credentials. `init-env.py` fills missing passwords,
preserves existing values, and restricts permissions to the owner. Compose loads
only the environment settings each container needs; only the agent gets the model
API key. Database and broker ports are never published to the host.

The default model is `gpt-5-nano`, selected for its low token prices and verified
account access. It is currently marked deprecated by OpenAI; the name is configurable
through `OPENAI_MODEL`. Pricing references: [Nano](https://developers.openai.com/api/docs/models/gpt-5-nano),
[Luna](https://developers.openai.com/api/docs/pricing). A valid API key can still lack
billing credit: the first real run verifies paid inference, not just key validity.

Use `AGENT_MODE=fake docker compose up -d` to test the real MCP/database integration
without calling OpenAI. Fake results are explicitly labelled in the dashboard.
For Python hot reload (requires Node 22.12+ to build the frontend):

```sh
npm ci --prefix frontend
npm --prefix frontend run build
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
```

For frontend hot reload, run `npm --prefix frontend run dev` and open
<http://localhost:5173>; API requests proxy to the gateway on port 5180.
See [frontend/README.md](frontend/README.md) for the theme, routes, map and source layout.

Edit Java sources and run `docker compose up -d --build core` to rebuild that service.

## What to try

- Overview displays the three seeded zones through the Java API.
- **Run report now** (Overview or Schedule & runs) builds a surge and incentive report: it reads the
  `zone_snapshot` MCP tool for the configured window (default 24 h), fixed rules
  compute the proposals and their numbers, and the model only writes the reasons and a
  summary (`AGENT_MODE=fake` uses template text and makes no model call). The report is
  stored in the agent's own database (`GET /api/reports`) and a `report.ready` event goes
  to RabbitMQ through the agent's outbox. The window and email recipients are set with
  **Schedule & runs** (`PUT /api/schedule`: `window_hours`, `recipients`). The mailer emails it to the
  recipients through `SMTP_*` (see `.env.example`); with `make dev`, Mailpit catches the
  emails at http://localhost:8025. Each report in `GET /api/reports` shows its delivery
  state. Nothing is written to `core` by the agent. See [docs/surge-incentive-agent-plan.md](docs/surge-incentive-agent-plan.md).
- **Reports** lists each report: summary, proposals with their reasons, delivery state
  and zone metrics. **Approve** (after a confirmation) creates and approves the proposal
  in core through the gateway, under your admin login, with the numbers from the stored
  report (the browser only names the proposal). That creates the surge rule or driver
  incentive. **Reject** only records the decision. Each proposal can be decided once;
  expired ones can't be approved.
- Edit the five-field cron expression, IANA timezone and enabled switch, then save.
  Schedules are stored in the agent's database and start disabled. The Python
  scheduler runs alongside Agno; it polls every five seconds and skips missed slots.
  A database lock serializes manual and scheduled executions. Changes apply to
  future slots; disabling does not cancel a run already started.
- Run history shows trigger source, model, fake/live mode, status, actual tool calls,
  response and safe error category. Inference failures are not retried automatically.
- **Proposals** shows what is in core, including proposals approved from reports. A test
  proposal (without a type) exercises the Java transactional outbox → durable RabbitMQ
  queue → deduplicating activity worker; approving it only records the decision.

Every trigger shares a 30-second cooldown, one-running-at-a-time lock, 100-second
run timeout, a hard two-model-request limit, 4,000 output-token cap per model call, and a default
30-runs-per-UTC-day limit (failed attempts count too). A report run makes one MCP call and
at most one model request, with no tools; none when no zone needs a proposal. No free-form paid prompt endpoint is
exposed. Limits bound usage; they are not a provider-side dollar budget.

## Services

| Service | Implementation | Owns |
| --- | --- | --- |
| core | Java 21 / Spring Boot | core database, seeded rows, proposals, outbox |
| worker | Python / aio-pika / FastAPI | activity database built from RabbitMQ events |
| mcp | Python / FastMCP | read-only zone analytics tools calling core with the READER login |
| agent | Python / Agno / FastAPI / croniter | agent database, cron schedule, run history, reports, report outbox |
| mailer | Python / aio-pika / smtplib | emails each `report.ready` (queue `unter.reports`); records delivery state in the agent database |
| gateway | Python / FastAPI + React / Material UI dashboard and ride PWA | one browser entry point and auth |
| postgres | PostgreSQL 17 | separate core, agent and activity databases/accounts |
| rabbitmq | RabbitMQ 4 | durable topic exchange, worker queue, mailer queue + retry queue |

Public routes: `/` (dashboard), `/ride/` (PWA), `/api/*` (admin Basic Auth), `/mcp` (admin Basic
Auth), `/healthz` (no application data). Internal services use automatically supplied
service Basic Auth. The Java OpenAPI document is available through `/api/openapi`.
Browser mutations require `X-Unter-Request: 1` to prevent cross-origin form attacks.

## Checks

Run `npm ci --prefix frontend`, `npm --prefix frontend run build`, and
`npm --prefix frontend test` for frontend lifecycle tests. Worker isolation checks run
with `node --test .github/scripts/*.test.cjs` after the build.


```sh
uv run --project services/python pytest services/python/tests -q
AGENT_MODE=fake docker compose up -d --build
uv run --project services/python python scripts/integration.py
make migrations-check   # fresh, legacy and incremental Alembic upgrades
make readonly-check     # the MCP server's READER login can't write to core
make stats-check        # /stats endpoints and MCP tools count a known scenario
uv run --project services/python python scripts/scan-secrets.py
```

CI runs all of these. The unit tests include `test_deploy_manifests.py`, which fails when the
Kubernetes manifests drift from `scripts/generate-manifests.py`, reference a Secret key that
`sync-secrets.py` doesn't copy, or lack a network-policy path a pod is configured for.

The integration check exercises auth/CSRF, seeded data, remote MCP discovery and
reads, schedule and report settings, proposal events, worker delivery, a report run, its
stored report, `report.ready` delivery, the mailer's delivery record, report decisions and
the cooldown. It creates a rejected test proposal, a run and a report. Run it against a
fresh local stack with scheduling disabled. It never prints credentials or model
responses. To test real inference, start the stack with `AGENT_MODE=live` instead.

For deterministic map providers during integration checks:

```sh
COMPOSE_FILE=compose.yaml:compose.test.yaml AGENT_MODE=fake docker compose up -d --build
COMPOSE_FILE=compose.yaml:compose.test.yaml make ride-check
BROWSER=chromium-browser uv run --project services/python python scripts/ride-browser-check.py
```

These checks create profiles, trips, reports and rules. Use an isolated stack with scheduling
disabled and other drivers offline. `compose.test.yaml` is test-only and is never deployed.
The browser check exercises address selection, estimated fare, road guidance, the full ride lifecycle,
mock earnings/history, mobile layout, reload recovery and service-worker cache isolation.

## Concurrent market simulation

`make simulate` runs parallel rider and driver clients through the real gateway, with
random traffic, rotating demand hotspots and deliberate booking/offer transition races.
It retains trips and events for analytics and writes timestamped timings, checks and
stats snapshots under `.local/simulations/`. Use an isolated local or staging stack;
startup refuses existing active traffic. See [client simulator](docs/client-simulator.md)
for soak runs, configuration, cleanup and evidence. CI runs a short simulation and saves
its evidence as an artifact.

## Deployment

See [deploy/README.md](deploy/README.md). Successful pushes to `main` run checks,
build SHA-tagged GHCR images, publish a full manifest snapshot on the generated
`deployments` branch, and let Flux reconcile. Never merge that generated branch
back into `main`. CI does not receive the OpenAI key or production credentials.

## Database migration history

All three databases have versioned schema tracking: Flyway for `core`, and separate
Alembic histories for `agent` and `activity`. Services automatically apply pending
migrations on startup, including fresh local installations. The initial Python
revisions safely adopt compatible existing tables without losing their records.

See [database migrations](docs/database-migrations.md) for current-version commands,
adding migrations, using another local database, migration tests and dump/restore.
