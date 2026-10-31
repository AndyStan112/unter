CREATE TABLE observations (
  zone text PRIMARY KEY, demand integer NOT NULL, drivers integer NOT NULL,
  wait_minutes integer NOT NULL
);
INSERT INTO observations VALUES ('Centru',12,8,3), ('Iosefin',18,2,11), ('Fabric',5,7,2);
CREATE TABLE proposals (
  id uuid PRIMARY KEY, zone text NOT NULL REFERENCES observations(zone),
  reason text NOT NULL, status text NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE outbox (id uuid PRIMARY KEY, kind text NOT NULL, payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), sent boolean NOT NULL DEFAULT false);
INSERT INTO outbox(id,kind,payload) VALUES
 ('00000000-0000-0000-0000-000000000001','observation.created','{"zone":"Centru","demand":12,"drivers":8,"wait_minutes":3}'),
 ('00000000-0000-0000-0000-000000000002','observation.created','{"zone":"Iosefin","demand":18,"drivers":2,"wait_minutes":11}'),
 ('00000000-0000-0000-0000-000000000003','observation.created','{"zone":"Fabric","demand":5,"drivers":7,"wait_minutes":2}');
