ALTER TABLE trips ADD COLUMN incentive_id uuid REFERENCES driver_incentives(id),
  ADD COLUMN driver_bonus numeric(10,2) NOT NULL DEFAULT 0 CHECK (driver_bonus >= 0);

-- Immutable settlement: the trip is the idempotency key. Money stays entirely simulated.
CREATE TABLE driver_earnings (
  trip_id uuid PRIMARY KEY REFERENCES trips(id),
  driver_id uuid NOT NULL REFERENCES drivers(id),
  fare numeric(12,2) NOT NULL CHECK (fare >= 0),
  bonus numeric(12,2) NOT NULL CHECK (bonus >= 0),
  total numeric(12,2) GENERATED ALWAYS AS (fare + bonus) STORED,
  currency text NOT NULL DEFAULT 'RON' CHECK (currency = 'RON'),
  payment_status text NOT NULL DEFAULT 'mock_settled' CHECK (payment_status = 'mock_settled'),
  settled_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX driver_earnings_history ON driver_earnings(driver_id, settled_at DESC);
CREATE INDEX trips_rider_history ON trips(rider_id, requested_at DESC);
CREATE INDEX trips_driver_history ON trips(driver_id, requested_at DESC);

-- Earlier completed rides retain their historical fare; historical bonuses weren't captured.
INSERT INTO driver_earnings(trip_id,driver_id,fare,bonus,settled_at)
SELECT id,driver_id,price,0,completed_at FROM trips
WHERE status='COMPLETED' AND driver_id IS NOT NULL AND price IS NOT NULL;
