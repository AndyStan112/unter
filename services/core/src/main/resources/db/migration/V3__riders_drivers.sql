CREATE TABLE riders (
  id uuid PRIMARY KEY, name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
-- Drivers carry their last known position; zone is derived from it by core.
-- current_trip_id gets its foreign key once trips exist.
CREATE TABLE drivers (
  id uuid PRIMARY KEY, name text NOT NULL,
  status text NOT NULL DEFAULT 'OFFLINE' CHECK (status IN ('OFFLINE','AVAILABLE','OFFERED','ON_TRIP')),
  current_trip_id uuid,
  lat double precision CHECK (lat BETWEEN -90 AND 90),
  lon double precision CHECK (lon BETWEEN -180 AND 180),
  position_updated_at timestamptz,
  zone text REFERENCES zones(name),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((lat IS NULL) = (lon IS NULL))
);
CREATE INDEX drivers_available ON drivers (status) WHERE status = 'AVAILABLE';
