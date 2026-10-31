# Deployment on the shared K3s host

Unter uses the existing `andy@ssh.windogs.win` cluster and Caddy proxy. It does not
bootstrap another cluster or modify Cube Studio's Flux resources, namespace,
credentials, database, images, PVCs, or NodePort.

- Namespace: `unter`, with resource quota, private service accounts, and default-deny
  network policies. Only explicit intra-application paths, DNS, agent HTTPS egress,
  and Caddy ingress are allowed. The worker/core databases are not reachable from
  Cube Studio pods. The agent's public HTTPS egress permits external APIs, not just
  OpenAI; it does not grant private-network access.
- Persistent volumes: 4 GiB PostgreSQL, 2 GiB RabbitMQ, using existing local-path storage.
- Database accounts: separate passwords and databases for core, agent and activity.
- Flux resources: `unter` in `flux-system`, reading this public repository's
  `deployments` branch without a deploy key.
- Images: `ghcr.io/andystan112/unter-core` and `unter-python`, pinned to source SHA.
- Private gateway NodePort: `172.22.0.1:30574`, distinct from Cube Studio's `30573`.
  Existing K3s configuration restricts NodePorts to the Docker bridge.
- Public hostname: `https://unter.windogs.win`, routed by the block in `deploy/Caddyfile`.

## Initial setup

1. Push `main` and wait for the `release` workflow. Verify both GHCR packages are
   publicly pullable. If GitHub creates one as private, make it public once.
2. Run `scripts/bootstrap-deploy.sh` from the checkout. It automatically reads the
   local ignored `.env`, creates only the Unter namespace and Secret, then applies
   Unter's Flux source and reconciliation resource. Secret values travel only over
   SSH stdin and are never put in shell arguments or tracked files.
3. Wait for Unter workloads to become ready. Validate through the private endpoint
   from the Caddy container before changing public routes.
4. Run `uv run --project services/python python scripts/configure-caddy.py`. It
   checks the private gateway, backs up the existing Caddyfile, appends only Unter,
   validates inside `windogs-proxy`, and reloads, restoring the original on failure.
   Check Unter and Cube Studio afterward.

Existing cluster-admin access is through `/home/andy/.kube/cube-studio.yaml` on the
server. Its filename identifies the original bootstrap, not shared application
configuration. No credential from that file is copied into this repository.

## Secrets and future changes

`uv run --project services/python python scripts/sync-secrets.py` copies credentials
from the local `.env` into the existing Unter Secret. It does not generate replacement
values. Restart the affected deployments after changes; environment settings load
when a pod starts. Routine CI/Flux releases preserve the existing Secret.

Database and RabbitMQ passwords are initialized on the first persistent-volume
startup. Changing them in `.env` later also requires rotating the corresponding
server-side account; simply replacing a Secret does not alter stored passwords.
Keep a secure copy of `.env` if you change machines. Never use `docker compose config`
or unrestricted pod environment dumps in public logs: they can resolve secrets.

Edit manifests directly, or regenerate them with
`uv run --project services/python python scripts/generate-manifests.py`. Review the
result before committing. The generator has no secret inputs.

## Rollback and persistence

Restore a previous manifest snapshot on `deployments` to roll back a release. Flux
applies it without triggering a build. The next successful `main` release replaces
that snapshot. Database migrations require their own rollback plan.

Do not delete the namespace or PVCs to roll back application code. Stateful data
lives on this single server and is not highly available. For this seeded skeleton,
no backup CronJob is installed; add database backups before storing valuable data.

## Schema migrations

The core service uses Flyway. Agent and worker run their own Alembic migration
chains before starting. Their first tracked revisions validate and adopt the
original unversioned tables, preserving existing rows and schedule settings.
No manual stamp or database recreation is required. A mismatch prevents startup
and rolls back schema/version changes. Each Python database has its own
`alembic_version`; core retains `flyway_schema_history`.

See [database migrations](../docs/database-migrations.md) for operational commands
and compatibility/rollback details. CI tests fresh installs and legacy adoption
before publishing images. Secrets and database ownership stay unchanged.
