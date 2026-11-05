-- The stats endpoints read every trip requested in a time window, across all zones. trips_zone_requested
-- leads with zone, so it can't serve that range on its own.
CREATE INDEX trips_requested ON trips (requested_at);
