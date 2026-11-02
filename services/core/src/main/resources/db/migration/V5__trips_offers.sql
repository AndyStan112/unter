CREATE TABLE trips (
  id uuid PRIMARY KEY,
  rider_id uuid NOT NULL REFERENCES riders(id),
  driver_id uuid REFERENCES drivers(id),
  zone text NOT NULL REFERENCES zones(name),
  pickup_lat double precision NOT NULL CHECK (pickup_lat BETWEEN -90 AND 90),
  pickup_lon double precision NOT NULL CHECK (pickup_lon BETWEEN -180 AND 180),
  dropoff_lat double precision NOT NULL CHECK (dropoff_lat BETWEEN -90 AND 90),
  dropoff_lon double precision NOT NULL CHECK (dropoff_lon BETWEEN -180 AND 180),
  status text NOT NULL DEFAULT 'REQUESTED'
    CHECK (status IN ('REQUESTED','OFFERED','ASSIGNED','PICKED_UP','COMPLETED','CANCELLED','UNMATCHED')),
  surge_multiplier numeric(3,2),
  price numeric(10,2),
  requested_at timestamptz NOT NULL DEFAULT now(),
  assigned_at timestamptz, picked_up_at timestamptz, completed_at timestamptz, cancelled_at timestamptz
);
CREATE TABLE offers (
  id uuid PRIMARY KEY,
  trip_id uuid NOT NULL REFERENCES trips(id),
  driver_id uuid NOT NULL REFERENCES drivers(id),
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','ACCEPTED','REJECTED','EXPIRED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  responded_at timestamptz
);
ALTER TABLE drivers ADD CONSTRAINT drivers_current_trip_fkey FOREIGN KEY (current_trip_id) REFERENCES trips(id);

-- Last line of defence: even a bug in core cannot double-book a driver or a trip.
CREATE UNIQUE INDEX one_active_trip_per_driver ON trips (driver_id) WHERE status IN ('ASSIGNED','PICKED_UP');
CREATE UNIQUE INDEX one_open_trip_per_rider ON trips (rider_id) WHERE status IN ('REQUESTED','OFFERED','ASSIGNED','PICKED_UP');
CREATE UNIQUE INDEX one_pending_offer_per_driver ON offers (driver_id) WHERE status = 'PENDING';
CREATE UNIQUE INDEX one_pending_offer_per_trip ON offers (trip_id) WHERE status = 'PENDING';

CREATE INDEX trips_zone_requested ON trips (zone, requested_at);
CREATE INDEX trips_waiting ON trips (requested_at) WHERE status = 'REQUESTED';
CREATE INDEX offers_trip ON offers (trip_id);
CREATE INDEX offers_pending_expiry ON offers (expires_at) WHERE status = 'PENDING';
