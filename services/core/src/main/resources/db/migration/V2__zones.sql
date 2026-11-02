-- Zones become their own table with a center point; a location belongs to the nearest center.
-- The demo observations table stays (dashboard, MCP and integration checks still read it).
CREATE TABLE zones (
  name text PRIMARY KEY,
  lat double precision NOT NULL CHECK (lat BETWEEN -90 AND 90),
  lon double precision NOT NULL CHECK (lon BETWEEN -180 AND 180)
);
INSERT INTO zones VALUES ('Centru',45.7537,21.2257), ('Iosefin',45.7480,21.2080), ('Fabric',45.7590,21.2430);

-- Existing proposals keep their zone; only the referenced table changes.
ALTER TABLE proposals DROP CONSTRAINT proposals_zone_fkey,
  ADD CONSTRAINT proposals_zone_fkey FOREIGN KEY (zone) REFERENCES zones(name);
ALTER TABLE observations ADD CONSTRAINT observations_zone_fkey FOREIGN KEY (zone) REFERENCES zones(name);
