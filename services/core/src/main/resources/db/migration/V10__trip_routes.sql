ALTER TABLE trips ADD COLUMN distance_meters numeric(12,2),
  ADD COLUMN duration_seconds numeric(12,2),
  ADD COLUMN distance_source text NOT NULL DEFAULT 'straight_line',
  ADD COLUMN pickup_label text, ADD COLUMN dropoff_label text;
