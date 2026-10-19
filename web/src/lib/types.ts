// Mirrors the engine's pydantic models (src/helixtune/model.py).

export type Role = 'tweeter' | 'midrange' | 'midbass' | 'woofer' | 'subwoofer' | 'fullrange' | 'unused'
export type EqType = 'peak' | 'low_shelf' | 'high_shelf' | 'notch' | 'allpass'
export type XoType = 'linkwitz_riley' | 'butterworth' | 'bessel'

export interface Crossover { type: XoType; slope_db: number; freq_hz: number }
export interface EqBand { enabled: boolean; type: EqType; freq_hz: number; gain_db: number; q: number }
export interface Channel {
  id: string; name: string; role: Role; gain_db: number; mute: boolean; invert: boolean
  delay_ms: number; hp: Crossover | null; lp: Crossover | null; eq: EqBand[]
  mix: Record<string, number>
  link_group: number
}
export interface Tune {
  name: string; device: string; sample_rate: number; master_gain_db: number
  channels: Channel[]; notes: string
}
export interface Device {
  kind: 'none' | 'emulator' | 'serial'; port: string | null; model: string | null
  writes_enabled: boolean; baselined: boolean
  sync_state: 'disconnected' | 'unsynchronized' | 'applying' | 'synchronized' | 'uncertain'
  last_error: string | null
  /** a missed keep-alive: every write is refused until disconnect + reconnect */
  needs_reconnect?: boolean
}
export interface EngineEvent { ts: number; source: string; summary: string; writes: number }
export interface OutputProtection {
  min_hp_hz: number | null; min_hp_slope_db: number; max_lp_hz: number | null; fs_factor: number
}
export interface ProposalInfo { id: string; title: string; kind: string; changes: number; source: string }
export interface ABState { A: string | null; B: string | null; active: 'A' | 'B' | null }
export interface Status {
  demo: boolean
  /** server started with --allow-physical-writes (supervised write sessions on a real DSP) */
  physical_writes_allowed?: boolean
  /** false while a real DSP is attached: master gain stays in the workstation and is not sent */
  master_on_device?: boolean
  /** output -> level it played at before being muted (this connection); unmuting at or below it is direct */
  unmute_levels?: Record<string, number>
  /** safety-relevant state restored from a backup; DSP writes stay blocked until acknowledged */
  state_faults?: string[]
  /** automated seat measurement (pink noise + RTA per output) */
  measure_run?: MeasureRunState | null
  interrupted_measure_run?: (Partial<MeasureRunState> & { error?: string }) | null
  connection_epoch: number
  device: Device; tune_name: string; revision: number; undo_depth: number; redo_depth?: number
  save_error?: string | null; recovery_notice?: string | null
  pending_writes: number | null; recent_events: EngineEvent[]
  ab: ABState; proposals: ProposalInfo[]
  /** yellow tier: allowed settings below a recommended (not enforced) margin */
  advisories?: string[]
}
export interface Proposal {
  id: string; kind: string; title: string; notes: string[]; source: string
  edits: { channel: string | null; field: string; label: string }[]
  metrics: Record<string, any>
}
export interface SystemView {
  seat: string; freqs: number[]; target_name: string; measurement_count: number
  measured: number[] | null; predicted: number[] | null; target: number[] | null
  groups: Record<string, number[]>; channels: Record<string, number[]>
  available_measurement_count: number; phase_verified: boolean
  aggregation: 'none' | 'single_capture' | 'power_sum'
  coverage: { outputs: string[]; missing_outputs: string[] }
  contributors: { id: string; name: string; channels: string[]; fingerprint: string; taken_at: number; frequency_range_hz: number[] }[]
  excluded: { id: string; name: string; reason: string }[]
  limitations: string[]
}
export interface ResponseView { freqs: number[]; channels: Record<string, number[]> }

export const ROLE_COLORS: Record<Role, string> = {
  subwoofer: 'var(--c-sub)', woofer: 'var(--c-sub)', midbass: 'var(--c-midbass)',
  midrange: 'var(--c-mid)', tweeter: 'var(--c-tweeter)', fullrange: 'var(--c-full)', unused: 'var(--muted)',
}
export const ROLE_LABEL: Record<Role, string> = {
  subwoofer: 'Sub', woofer: 'Woofer', midbass: 'Midbass', midrange: 'Midrange',
  tweeter: 'Tweeter', fullrange: 'Full range', unused: 'Unused',
}

// ---- system design (src/helixtune/equipment.py) ----
export type Kind = 'source' | 'interface' | 'dsp' | 'controller' | 'amplifier' | 'speaker' | 'subwoofer' | 'enclosure' | 'microphone' | 'power' | 'computer' | 'other'
export type Signal = 'speaker' | 'line' | 'high_level' | 'optical' | 'coax' | 'usb' | 'data' | 'power' | 'ground' | 'remote' | 'other'
export interface Spec { value: number | string; unit: string; source: string }
export interface Component {
  id: string; kind: Kind; name: string; make: string; model: string; serial: string; location: string
  channels: string[]; enclosure: string | null; specs: Record<string, Spec>; spec_source: string; notes: string
  image: string | null; media: string[]; flow_pos: XY | null; cab_pos: XY | null
}
export interface XY { x: number; y: number }
export interface MediaItem { id: string; url: string; filename: string; content_type: string; size: number; caption: string; tags: string[]; created: number }
export interface Connection { id: string; src: string; src_port: string; dst: string; dst_port: string; signal: Signal; cable: string; notes: string }
export interface Vehicle { year: string; make: string; model: string; trim: string; notes: string; layout_image: string | null; media: string[] }
export interface Design { vehicle: Vehicle; components: Component[]; connections: Connection[] }
export interface Analysis { id: string; label: string; findings: string[]; derived: Record<string, number> }
export type SpecFields = Record<string, Record<string, { label: string; unit: string }>>

export const KIND_LABEL: Record<Kind, string> = {
  source: 'Source', interface: 'Interface', dsp: 'DSP', controller: 'Controller', amplifier: 'Amplifier', speaker: 'Speaker', subwoofer: 'Subwoofer',
  enclosure: 'Enclosure', microphone: 'Microphone', power: 'Power', computer: 'Computer', other: 'Other',
}
export const SIGNAL_STYLE: Record<Signal, { label: string; color: string; dash?: string }> = {
  speaker: { label: 'Speaker wire', color: 'var(--c-midbass)' },
  line: { label: 'RCA / line', color: 'var(--c-tweeter)' },
  high_level: { label: 'High-level in', color: 'var(--c-sub)' },
  optical: { label: 'Optical', color: 'var(--c-full)', dash: '6 4' },
  coax: { label: 'Coax digital', color: 'var(--c-full)', dash: '2 3' },
  usb: { label: 'USB', color: 'var(--muted)', dash: '6 4' },
  data: { label: 'Data / control', color: 'var(--ink)', dash: '2 4' },
  power: { label: '+12 V power', color: 'var(--warn)' },
  ground: { label: 'Ground', color: 'var(--dim)' },
  remote: { label: 'Remote turn-on', color: 'var(--ok)', dash: '2 3' },
  other: { label: 'Other', color: 'var(--muted)' },
}

export type Source = 'L' | 'R' | 'mono' | 'off' | 'custom'
export const SOURCE_MIX: Record<Exclude<Source, 'custom'>, Record<string, number>> = {
  L: { L: 1 }, R: { R: 1 }, mono: { L: 0.5, R: 0.5 }, off: {},
}
export function sourceOf(mix: Record<string, number>): Source {
  const l = mix.L ?? 0, r = mix.R ?? 0
  if (!l && !r) return 'off'
  if (l === 1 && !r) return 'L'
  if (r === 1 && !l) return 'R'
  if (l === 0.5 && r === 0.5) return 'mono'
  return 'custom'
}
export const SOURCE_LABEL: Record<Source, string> = { L: 'Left', R: 'Right', mono: 'Mono L+R', off: 'Off', custom: 'Custom mix' }

export interface ProtectionConstraint {
  id: string; output: string; field: 'min_hp_hz' | 'min_hp_slope_db' | 'max_lp_hz' | 'fs_factor'
  value: number; unit: string; source: Record<string, unknown>; current: boolean
  state: 'pending' | 'confirmed' | 'cleared'; fingerprint: string
  /** yellow tier: reported, not enforced, because a manufacturer minimum governs */
  advisory?: boolean
  history: { action: string; actor: string; reason: string; at: number }[]
}

export interface MeasureRunState {
  id: string; outputs: string[]; seat: string; seconds: number; settle_s: number; level_dbfs: number
  source: 'rew' | 'external'; status: 'running' | 'done' | 'stopped' | 'failed'
  phase: string; current: string | null; step: number; remaining_s: number
  captures: { output: string; measurement_id: string; rew_uuid: string }[]
  error: string | null; changed: string[]; restored: boolean
  kind?: 'measure' | 'align'
  delay_changed?: string[]
  align?: { reference: string; adjust: string; carry: string[]; fc: number; offsets: number[]
            results: { offset_ms: number; band_db: number }[]; best_offset_ms?: number; gain_db?: number
            outcome?: string; proposal_id?: string } | null
}
