export interface Schedule {
  cron: string;
  timezone: string;
  enabled: boolean;
  window_hours: number;
  recipients: string[];
  next_at: string | null;
  model: string;
  mode: string;
  max_daily_runs: number;
}
export interface Observation {
  zone: string;
  demand: number;
  drivers: number;
  wait_minutes: number;
}
export interface Run {
  id: string;
  status: string;
  source: string;
  started_at: string;
  model: string;
  mode: string;
  tool_calls: string[];
  result?: string;
  error?: string;
}
export interface ProposalParams {
  multiplier?: number;
  bonus_per_trip?: number;
  starts_at: string;
  ends_at: string;
}
export interface Proposal {
  id: string;
  zone: string;
  type: 'surge' | 'incentive' | null;
  params: ProposalParams;
  reason: string;
  status: string;
  rule?: string;
}
export interface ZoneMetrics {
  zone: string;
  requests: number;
  requests_per_hour: number;
  unmatched_rate: number | null;
  cancel_rate: number | null;
  worst_p90_wait_s: number | null;
  net_flow: number;
  supply_now?: { available: number };
  demand_supply_ratio: number | null;
}
export interface Report {
  id: string;
  created_at: string;
  published: boolean;
  report: {
    summary: string;
    proposals: Proposal[];
    explained_by: string;
    model: string;
    window: { from: string; to: string };
    zones: ZoneMetrics[];
    skipped: { zone: string; reason: string }[];
  };
  delivery?: { status: string; last_error?: string };
  decisions?: Record<string, { status: string }>;
}
export interface ActivityEvent {
  id: string;
  kind: string;
  created_at: string;
  payload: unknown;
}
