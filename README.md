# Unter

A deliberately small distributed application: seeded PostgreSQL rows, a Java API,
RabbitMQ events, a Python worker and read-only MCP server, an Agno agent that proposes
surge rates and driver incentives in a report, and an
installable admin PWA. No ride-hailing platform is implemented.

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

Open <http://localhost:5180>. The data requests ask for the `ADMIN_USERNAME` and
`ADMIN_PASSWORD` from `.env` once; the browser reuses Basic Auth on this origin.
Static PWA assets are public and contain no application data or credentials.
All data, administration and MCP access require authentication. The PWA only
caches static assets and shows an offline notice when live requests are unavailable.

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
For Python/UI hot reload:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d --build
```

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
| gateway | Python / FastAPI + buildless JS/CSS PWA | one browser entry point and auth |
| postgres | PostgreSQL 17 | separate core, agent and activity databases/accounts |
| rabbitmq | RabbitMQ 4 | durable topic exchange, worker queue, mailer queue + retry queue |

Public routes: `/` (static PWA), `/api/*` (admin Basic Auth), `/mcp` (admin Basic
Auth), `/healthz` (no application data). Internal services use automatically supplied
service Basic Auth. The Java OpenAPI document is available through `/api/openapi`.
Browser mutations require `X-Unter-Request: 1` to prevent cross-origin form attacks.

## Checks

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
