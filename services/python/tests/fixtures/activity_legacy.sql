-- Schema deployed before Alembic was introduced. Keep this fixture unchanged.
CREATE TABLE activity (
    id text PRIMARY KEY, kind text NOT NULL, payload jsonb NOT NULL, created_at timestamptz DEFAULT now()
);
INSERT INTO activity(id,kind,payload) VALUES ('legacy-event','migration.test','{"preserve":true}');
