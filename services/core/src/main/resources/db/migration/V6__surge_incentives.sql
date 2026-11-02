-- Proposals gain a kind and its parameters. Older proposals have neither: approving one changes nothing.
ALTER TABLE proposals
  ADD COLUMN type text CHECK (type IN ('surge','incentive')),
  ADD COLUMN params jsonb,
  ADD COLUMN decided_at timestamptz,
  ADD CONSTRAINT proposals_params_with_type CHECK ((type IS NULL) = (params IS NULL));

-- Created when a proposal is approved. Where windows overlap, the newest rule for a zone applies.
CREATE TABLE surge_rules (
  id uuid PRIMARY KEY,
  zone text NOT NULL REFERENCES zones(name),
  multiplier numeric(3,2) NOT NULL CHECK (multiplier BETWEEN 1.00 AND 3.00),
  starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL CHECK (ends_at > starts_at),
  proposal_id uuid REFERENCES proposals(id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE driver_incentives (
  id uuid PRIMARY KEY,
  zone text NOT NULL REFERENCES zones(name),
  bonus_per_trip numeric(5,2) NOT NULL CHECK (bonus_per_trip BETWEEN 0 AND 20),
  starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL CHECK (ends_at > starts_at),
  proposal_id uuid REFERENCES proposals(id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX surge_rules_zone_window ON surge_rules (zone, ends_at);
CREATE INDEX driver_incentives_zone_window ON driver_incentives (zone, ends_at);
