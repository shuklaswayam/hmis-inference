/**
 * Shared inference types extracted from the backend envelope.
 *
 * Keep these in sync with /api/v1/inference/* responses:
 *   { workstream, data, severity, confidence, generated_at,
 *     expires_at, trace_id, cache_hit }
 */

export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

export interface InferenceEnvelope<TData = unknown> {
  workstream: 'outbreak_risk' | 'hospital_pressure' | 'priority_rank' | 'policy_memo'
  data: TData
  severity?: Severity | null
  confidence?: number | null
  generated_at?: string
  expires_at?: string
  trace_id?: string
  cache_hit?: boolean
}

export interface OutbreakSignal {
  district_id: string
  district_name: string
  disease_name: string
  tier: 'Low' | 'Medium' | 'High' | 'Critical'
  confidence: number
  cases_last_14d: number
  baseline_ratio: number
  deaths_last_14d: number
  one_liner: string
  recommended_action: string
  contributing_signals: string[]
}

export interface PressureSignal {
  facility_id: string
  facility_name: string
  district_name: string
  tier: 'Normal' | 'Strained' | 'Critical'
  confidence: number
  icu_occupancy_pct: number
  bed_occupancy_pct: number
  trend_48h: 'rising' | 'stable' | 'easing'
  trend_confidence: number
  projection_available: boolean
  icu_pred_24h: number | null
  icu_pred_48h: number | null
  bed_pred_48h: number | null
  one_liner: string
  recommended_action: string
}

export interface RankedAction {
  rank: number
  headline: string
  severity: Severity
  severity_score: number
  recommended_owner: string
  sla_hours: number
  evidence_refs: string[]
  recommended_step: string
}

export interface MemoAction {
  action: string
  owner: string
  sla_hours: number
  /** Rich 2-4 sentence description: what is happening, magnitude, and why it matters today */
  description?: string
  /** 1-2 sentence justification naming specific evidence and bundle fields */
  rationale?: string
  /** 3-6 concrete bullets the owner can execute */
  next_steps?: string[]
  severity?: Severity
  evidence_refs?: string[]
  /** Optional deep-link to the underlying source data */
  source_url?: string
}

export interface PolicyMemoBody {
  headline: string
  body_md: string
  recommended_actions: MemoAction[]
  llm_generated: boolean
}

export type OutbreakRiskEnvelope = InferenceEnvelope<{
  signals: OutbreakSignal[]
  count: number
}>
export type HospitalPressureEnvelope = InferenceEnvelope<{
  signals: PressureSignal[]
  count: number
}>
export type PriorityRankEnvelope = InferenceEnvelope<{
  ranked: RankedAction[]
  count: number
}>
export type PolicyMemoEnvelope = InferenceEnvelope<PolicyMemoBody>
