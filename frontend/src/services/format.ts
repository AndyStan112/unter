import type { Proposal } from '../types/dashboard';
export const date = (value: string | null) =>
  value
    ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
    : '—';
export const percent = (value: number | null) =>
  value == null ? '—' : `${Math.round(value * 100)}%`;
export const amount = (proposal: Proposal) =>
  proposal.type === 'surge'
    ? `Surge ×${proposal.params.multiplier}`
    : proposal.type === 'incentive'
      ? `Driver bonus ${proposal.params.bonus_per_trip} RON / trip`
      : 'Test proposal';
