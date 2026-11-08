# Database migrations

All three application databases have versioned migration histories committed to Git.
There is one PostgreSQL instance, with a separate database and account per service.

| Database | Tool | Migration files | History table |
| --- | --- | --- | --- |
| core | Flyway | `services/core/src/main/resources/db/migration/` | `flyway_schema_history` |
| agent | Alembic | `services/python/unter/migrations/agent/versions/` | `alembic_version` in agent |
| activity | Alembic | `services/python/unter/migrations/activity/versions/` | `alembic_version` in activity |

Normal service startup applies pending migrations before serving requests or
consuming events. Migration failure prevents that service from starting. Alembic
runs its schema operations and version updates in a PostgreSQL transaction under
a database advisory lock, so simultaneous starts cannot race the version check.
The core service retains Flyway's existing startup migration behavior.

## Local setup and current versions

`make up` creates the databases with separate accounts, applies all migrations and
loads the example rows through Flyway. PostgreSQL's initialization script only
creates databases and accounts; application schemas belong in migration files.
Existing volumes are upgraded in place. No manual schema SQL or stamp is needed.

```sh
docker compose exec -T agent python -m unter.migrate current
docker compose exec -T worker python -m unter.migrate current
docker compose exec -T agent python -m unter.migrate history
docker compose exec -T worker python -m unter.migrate history
docker compose exec -T postgres psql -U unter -d core -c \
  'SELECT version, description, success FROM flyway_schema_history ORDER BY installed_rank'
```

Apply pending Python migrations explicitly when necessary:

```sh
docker compose exec -T agent python -m unter.migrate upgrade
docker compose exec -T worker python -m unter.migrate upgrade
```

The commands reuse each container's configured credentials. They never need the
OpenAI key and do not run the agent task.

## Adding schema changes

Never edit, delete or renumber an applied migration. Keep historical revisions and
the initial baseline helper unchanged, and add a new revision for each schema
change. Commit the migration together with the code that needs it, using a
Conventional Commit message such as `feat(agent): store run duration`.

For Java, add `V2__description.sql`, then `V3__description.sql`, etc. Flyway records
versions and checksums. For Python, generate a revision in the correct chain:

```sh
uv run --project services/python alembic -c services/python/alembic.ini -n agent \
  revision -m "add run duration"
uv run --project services/python alembic -c services/python/alembic.ini -n activity \
  revision -m "add event source"
```

Fill in `upgrade()` and `downgrade()` using Alembic operations. A migration may use
SQL through `op.execute()` when appropriate. These services use psycopg queries,
not SQLAlchemy ORM models, so automatic model-diff generation is not configured.
Review generated revisions before running them. Migrations run inside the same
versioned container image as their service.

Use additive changes for deployments that need compatibility with older app
versions. Renames, drops and data conversions need an explicit compatibility and
recovery plan; reverting an image does not undo database migrations.

## Existing databases from the original skeleton

Current Alembic revisions:

| Chain | Revision | Adds |
|---|---|---|
| agent | `agent_0001` | `schedule`, `runs` (adopts the original tables) |
| agent | `agent_0002` | `report_settings` (one row), `reports`, `agent_outbox` |
| agent | `agent_0003` | `report_deliveries` (written by the mailer, which uses the agent login) |
| agent | `agent_0004` | `report_decisions` (approve/reject per reported proposal) |
| activity | `activity_0001` | `activity` (adopts the original table) |

All later revisions only add tables, so an older agent image keeps working against them.

The initial Alembic revisions are `agent_0001` and `activity_0001`. For an empty
database they create the tables. For an existing unversioned database, they verify
column types, nullability, defaults, primary keys and check/unique/foreign-key
constraints against the original schema, preserve records and schedule settings,
and record the baseline version in the same transaction. They can also finish a
partially created original schema without replacing existing valid tables.

An incompatible table stops the migration and rolls back new schema/version
changes. Inspect the mismatch and prepare an appropriate migration instead of
blindly stamping the database. Ordinary future revisions use explicit upgrade
operations; they do not rely on `CREATE TABLE IF NOT EXISTS`.

## Testing migrations

With the local stack running:

```sh
make migrations-check
```

The check creates temporary PostgreSQL databases with generated
`unter_migration_test_` names, then removes only those databases. It tests both
Python chains against empty schemas and historical unversioned schema fixtures,
checks that records and schedule settings survive adoption and repeated startup,
tests concurrent upgrades and an incremental upgrade/downgrade, rejects schema
drift, and verifies the Java Flyway history. CI runs it before release integration.
It does not invoke OpenAI or erase the normal local application databases.

To work against another PostgreSQL instance, put its `DB_HOST`, `DB_PORT`,
`DB_NAME`, `DB_USER` and `DB_PASSWORD` in an ignored `.env.db` file. Then, from the
repository root:

```sh
PYTHONPATH=services/python uv run --project services/python --env-file .env.db \
  python -m unter.migrate upgrade --service agent
```

Use `--service activity` for the worker's schema. The target database may have any
name; the explicit service selects its migration chain. Create the database and
account first, using an account that owns that database's schema. The Python
migration runner rejects `core`, whose schema belongs to Flyway.

## Downgrades and moving data

A downgrade requires an explicit revision, for example:

```sh
docker compose exec -T agent python -m unter.migrate downgrade agent_0001
```

Do this only after reviewing that revision's downgrade and stopping incompatible
application code. A downgrade to `base` drops the initial application tables and
their data. Startup otherwise upgrades back to the newest revision automatically.
Flyway migrations are forward-only in this setup; reverse changes require a new
reviewed SQL migration or restoring a compatible backup.

Migrations track schema evolution; moving populated databases between machines
also requires a database dump/restore. For example, back up the agent database:

```sh
mkdir -p .local/backups
(umask 077; docker compose exec -T postgres pg_dump -U unter -d agent -Fc \
  > .local/backups/agent.dump)
```

The dump includes `alembic_version`, so a restored database retains its version.
Restore into an empty target database before starting the service, preserving the
correct service's ownership. The corresponding restore inside a prepared target
Compose installation is:

```sh
docker compose exec -T postgres pg_restore -U unter --role=agent \
  --no-owner --no-privileges -d agent < .local/backups/agent.dump
```

Repeat with `core`/`activity` and their matching owner roles as needed. Dumps stay
under ignored `.local/`; they can contain application data and should not enter Git.
