-- now() is fixed per transaction, so created_at cannot order several events from one change.
-- A sequence keeps them in the order they were written; existing rows are numbered as stored.
ALTER TABLE outbox ADD COLUMN seq bigserial;
CREATE INDEX outbox_unsent ON outbox (seq) WHERE NOT sent;
