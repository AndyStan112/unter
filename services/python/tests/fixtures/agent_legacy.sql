-- Schema deployed before Alembic was introduced. Keep this fixture unchanged.
CREATE TABLE schedule (
    id integer PRIMARY KEY CHECK (id=1), cron text NOT NULL,
    timezone text NOT NULL, enabled boolean NOT NULL, next_at timestamptz NOT NULL
);
CREATE TABLE runs (
    id uuid PRIMARY KEY, source text NOT NULL, status text NOT NULL,
    mode text NOT NULL, model text NOT NULL, started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz, result text, error text, tool_calls jsonb
);
INSERT INTO schedule VALUES (1,'17 */4 * * *','Europe/Bucharest',false,'2026-11-01T12:00:00Z');
INSERT INTO runs(id,source,status,mode,model,result,tool_calls)
VALUES ('00000000-0000-0000-0000-000000000099','manual','completed','fake','test-model','Preserve this run','["list_observations"]');
