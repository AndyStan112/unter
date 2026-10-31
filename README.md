# Unter

A deliberately small distributed application: seeded PostgreSQL rows, a Java API,
RabbitMQ events, a Python worker and MCP server, an Agno hello-world agent, and an
installable admin PWA. No ride-hailing platform is implemented.

## Start locally

Prerequisites: Docker Compose and [uv](https://docs.astral.sh/uv/).

```sh
cp .env.example .env # only if .env does not already exist
# Set OPENAI_API_KEY in your editor. Never commit .env.
UV_CACHE_DIR=/tmp/unter-uv-cache uv sync --project services/python --frozen
UV_CACHE_DIR=/tmp/unter-uv-cache uv run --project services/python python scripts/init-env.py
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
- **Agent & schedule → Run hello world** forces an MCP `list_observations` tool
  call, then returns a model-generated greeting and the rows. The agent is given
  only that read tool, never the propose tool.
- Edit the five-field cron expression, IANA timezone and enabled switch, then save.
  Schedules are stored in the agent's database and start disabled. The Python
  scheduler runs alongside Agno; it polls every five seconds and skips missed slots.
  A database lock serializes manual and scheduled executions. Changes apply to
  future slots; disabling does not cancel a run already started.
- Run history shows trigger source, model, fake/live mode, status, actual tool calls,
  response and safe error category. Inference failures are not retried automatically.
- Create a test proposal to exercise the Java transactional outbox → durable
  RabbitMQ queue → deduplicating activity worker. Approve/reject only updates a
  demonstration status; it has no real-world effects.

Every trigger shares a 30-second cooldown, one-running-at-a-time lock, 100-second
run timeout, one tool-call limit, 1,200 output-token cap per model call, and a default
30-runs-per-UTC-day limit (failed attempts count too). A normal hello run makes two
model requests, around the single MCP call. No free-form paid prompt endpoint is
exposed. Limits bound usage; they are not a provider-side dollar budget.

## Services

| Service | Implementation | Owns |
| --- | --- | --- |
| core | Java 21 / Spring Boot | core database, seeded rows, proposals, outbox |
| worker | Python / aio-pika / FastAPI | activity database built from RabbitMQ events |
| mcp | Python / FastMCP | three remote Streamable HTTP tools calling core |
| agent | Python / Agno / FastAPI / croniter | agent database, cron schedule, run history |
| gateway | Python / FastAPI + buildless JS/CSS PWA | one browser entry point and auth |
| postgres | PostgreSQL 17 | separate core, agent and activity databases/accounts |
| rabbitmq | RabbitMQ 4 | durable topic exchange and worker queue |

Public routes: `/` (static PWA), `/api/*` (admin Basic Auth), `/mcp` (admin Basic
Auth), `/healthz` (no application data). Internal services use automatically supplied
service Basic Auth. The Java OpenAPI document is available through `/api/openapi`.
Browser mutations require `X-Unter-Request: 1` to prevent cross-origin form attacks.

## Checks

```sh
uv run --project services/python pytest services/python/tests -q
AGENT_MODE=fake docker compose up -d --build
uv run --project services/python python scripts/integration.py
uv run --project services/python python scripts/scan-secrets.py
```

The integration check exercises auth/CSRF, seeded data, remote MCP discovery and
reads, schedule persistence, proposal events, worker delivery, the agent and the
cooldown. It creates a rejected test proposal and a run record. Run it against a
fresh local stack with scheduling disabled. It never prints credentials or model
responses. To test real inference, start the stack with `AGENT_MODE=live` instead.

## Deployment

See [deploy/README.md](deploy/README.md). Successful pushes to `main` run checks,
build SHA-tagged GHCR images, publish a full manifest snapshot on the generated
`deployments` branch, and let Flux reconcile. Never merge that generated branch
back into `main`. CI does not receive the OpenAI key or production credentials.
