// Single client-side store. The engine is the source of truth: every edit goes through the
// API, then we re-read. Polling `revision` picks up edits made by agents or other devices.

import { sessionRequest } from './session'
import type { Channel, Component, Connection, Design, EqBand, OutputProtection, ProtectionConstraint, Proposal, ResponseView, SpecFields, Status, SystemView, Tune, Crossover, Vehicle } from './types'

export type Mode = 'studio' | 'drive' | 'setup' | 'system' | 'measurements'

class ApiError extends Error {
  constructor(public status: number, public body: any) {
    super(body?.conflicts ? `Proposal is out of date: ${body.conflicts.join('; ')}. Recompute it.`
      : body?.problems ? body.problems.join('; ')
      : (typeof body?.detail === 'string' ? body.detail : body?.detail ? JSON.stringify(body.detail) : `HTTP ${status}`))
  }
}

async function api<T = any>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await sessionRequest(path, {
    method,
    headers: body === undefined ? {} : { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new ApiError(r.status, j)
  return j as T
}

export interface Toast { id: number; text: string; kind: 'error' | 'info' }

class AppState {
  tune = $state<Tune | null>(null)
  status = $state<Status | null>(null)
  system = $state<SystemView | null>(null)
  electrical = $state<ResponseView | null>(null)
  selected = $state('C')
  mode = $state<Mode>('studio')
  seat = $state('driver')
  smoothing = $state(6)
  layers = $state({ target: true, measured: true, predicted: true, groups: true, electrical: false })
  snapshots = $state<string[]>([])
  toasts = $state<Toast[]>([])
  proposal = $state<Proposal | null>(null)       // the one open for review
  preview = $state<SystemView | null>(null)      // system view if it were applied
  proposalConflicts = $state<string[]>([])       // why the open proposal can no longer be applied
  busy = $state(false)
  design = $state<Design | null>(null)
  specFields = $state<SpecFields>({})
  protections = $state<Record<string, OutputProtection>>({})
  protectionConstraints = $state<Record<string, ProtectionConstraint>>({})
  selectedComponent = $state<string | null>(null)
  private pollTimer: ReturnType<typeof setInterval> | undefined
  private generation = 0
  private rev = -1
  private toastId = 0

  get channel(): Channel | undefined {
    return this.tune?.channels.find((c) => c.id === this.selected)
  }

  toast(text: string, kind: Toast['kind'] = 'error') {
    const t = { id: ++this.toastId, text, kind }
    this.toasts = [...this.toasts, t]
    setTimeout(() => (this.toasts = this.toasts.filter((x) => x.id !== t.id)), kind === 'error' ? 7000 : 2500)
  }

  async refresh(generation = this.generation) {
    const [tune, system, electrical, snaps, design, protections] = await Promise.all([
      api<Tune>('GET', '/api/tune'),
      api<SystemView>('GET', `/api/system?seat=${this.seat}&smoothing=${this.smoothing}&points=240`),
      api<ResponseView>('GET', '/api/response?points=240'),
      api<string[]>('GET', '/api/snapshots'),
      api<Design>('GET', '/api/design'),
      api<{ outputs: Record<string, OutputProtection>; constraints: Record<string, ProtectionConstraint> }>('GET', '/api/protections'),
    ])
    if (generation !== this.generation) return
    this.design = design
    this.protections = protections.outputs
    this.protectionConstraints = protections.constraints
    if (!Object.keys(this.specFields).length) this.specFields = await api<SpecFields>('GET', '/api/design/spec-fields')
    this.tune = tune
    this.system = system
    this.electrical = electrical
    this.snapshots = snaps
  }

  async poll() {
    const generation = this.generation
    try {
      const s = await api<Status>('GET', '/api/status')
      if (generation !== this.generation) return
      this.status = s
      if (s.revision !== this.rev) {
        this.rev = s.revision
        await this.refresh(generation)
        if (generation !== this.generation) return
        // a proposal opened elsewhere (e.g. by an agent) shows up for review here
        const latest = s.proposals.at(-1)
        if (latest && !this.proposal) await this.openProposal(latest.id)
        if (this.proposal && !s.proposals.some((p) => p.id === this.proposal!.id)) this.closeProposal()
        else if (this.proposal) await this.refreshPreview()
      }
    } catch {
      /* engine restarting; keep last state */
    }
  }

  start() {
    if (this.pollTimer !== undefined) return
    this.poll()
    this.pollTimer = setInterval(() => this.poll(), 1200)
  }

  stop() {
    clearInterval(this.pollTimer)
    this.pollTimer = undefined
    this.generation += 1
    this.rev = -1
    this.tune = null
    this.status = null
    this.system = null
    this.electrical = null
    this.design = null
    this.protections = {}
    this.protectionConstraints = {}
    this.snapshots = []
    this.closeProposal()
  }

  private async run(p: Promise<unknown>) {
    try {
      await p
    } catch (e: any) {
      this.toast(e.message ?? String(e))
    }
    await this.poll()
  }

  patchChannel(cid: string, fields: Partial<Channel>) {
    return this.run(api('PATCH', `/api/channels/${cid}`, fields))
  }
  reviewProtection(item: ProtectionConstraint, action: 'confirm' | 'clear', reason: string) {
    return this.run(api('POST', `/api/protections/constraints/${item.id}/review`, {
      action, reason, expected_fingerprint: item.fingerprint,
    }))
  }
  setCrossover(cid: string, which: 'hp' | 'lp', xo: Crossover | null) {
    return this.run(api('PUT', `/api/channels/${cid}/${which}`, xo))
  }
  patchBand(cid: string, band: number, fields: Partial<EqBand>) {
    return this.run(api('PATCH', `/api/channels/${cid}/eq/${band}`, fields))
  }
  setMaster(gain_db: number) {
    return this.run(api('PATCH', '/api/master', { gain_db }))
  }
  undo() {
    return this.run(api('POST', '/api/undo'))
  }
  redo() {
    return this.run(api('POST', '/api/redo'))
  }
  retrySave() {
    return this.run(api('POST', '/api/session/save'))
  }
  loadSnapshot(name: string) {
    return this.run(api('POST', `/api/snapshots/${encodeURIComponent(name)}/load`))
  }
  async saveSnapshot(name: string) {
    try {
      await api('POST', '/api/snapshots', { name })
      this.toast(`Saved “${name}”`, 'info')
    } catch (e: any) {
      // existing scenes are never replaced implicitly; ask the owner first
      if (e?.status === 409 && e?.body?.error === 'exists') {
        if (confirm(`A scene named “${e.body.name}” already exists. Replace it?`)) {
          await this.run(api('POST', '/api/snapshots', { name, overwrite: true }))
        }
      } else this.toast(e.message ?? String(e))
    }
    await this.poll()
  }
  // ---- proposals -------------------------------------------------------------------
  private async propose(path: string, body?: unknown) {
    this.busy = true
    try {
      const p = await api<Proposal>('POST', path, body)
      await this.openProposal(p.id)
      if (!p.edits.length) this.toast(p.notes.join(' ') || 'Nothing to change', 'info')
    } catch (e: any) {
      this.toast(e.message ?? String(e))
    } finally {
      this.busy = false
    }
  }
  proposeAutoEq(channels: string[] | null, opts: { max_bands?: number; max_freq?: number } = {}) {
    return this.propose('/api/propose/auto-eq', { channels, seat: this.seat, ...opts })
  }
  proposeLevels() {
    return this.propose(`/api/propose/levels?seat=${this.seat}`)
  }
  proposeAlignment(distances_cm: Record<string, number>) {
    return this.propose('/api/propose/alignment', { distances_cm })
  }
  async openProposal(id: string) {
    this.proposal = await api<Proposal>('GET', `/api/proposals/${id}`)
    await this.refreshPreview()
  }
  async refreshPreview() {
    if (!this.proposal) return
    try {
      this.preview = await api<SystemView>('GET', `/api/proposals/${this.proposal.id}/preview?seat=${this.seat}&smoothing=${this.smoothing}&points=240`)
      this.proposalConflicts = []
    } catch (e: any) {
      this.preview = null
      this.proposalConflicts = e?.body?.conflicts ?? [e.message ?? String(e)]
    }
  }
  closeProposal() {
    this.proposal = null
    this.preview = null
    this.proposalConflicts = []
  }
  /** Close the card only when the engine accepted it; a refusal keeps it open with its reasons. */
  async applyProposal(): Promise<boolean> {
    if (!this.proposal) return false
    const id = this.proposal.id
    try {
      await api('POST', `/api/proposals/${id}/apply`)
    } catch (e: any) {
      if (e?.status === 409 && Array.isArray(e?.body?.conflicts)) this.proposalConflicts = e.body.conflicts
      else this.toast(e?.message ?? String(e))
      await this.poll()
      return false
    }
    this.closeProposal()
    await this.poll()
    return true
  }
  async discardProposal() {
    if (!this.proposal) return
    const id = this.proposal.id
    this.closeProposal()
    await this.run(api('DELETE', `/api/proposals/${id}`))
  }

  // ---- system design ------------------------------------------------------------------
  async addComponent(c: Partial<Component>): Promise<Component | null> {
    let made: Component | null = null
    try {
      made = await api<Component>('POST', '/api/equipment', c)
      this.selectedComponent = made.id
    } catch (e: any) { this.toast(e.message) }
    await this.poll()
    return made
  }
  patchComponent(id: string, fields: Partial<Omit<Component, 'specs'>> & { specs?: Record<string, any> }) {
    return this.run(api('PATCH', `/api/equipment/${id}`, fields))
  }
  deleteComponent(id: string) {
    if (this.selectedComponent === id) this.selectedComponent = null
    return this.run(api('DELETE', `/api/equipment/${id}`))
  }
  addConnection(c: Partial<Connection>) {
    return this.run(api('POST', '/api/connections', c))
  }
  deleteConnection(id: string) {
    return this.run(api('DELETE', `/api/connections/${id}`))
  }
  setVehicle(v: Vehicle) {
    return this.run(api('PUT', '/api/design/vehicle', v))
  }
  async uploadMedia(file: File, caption = ''): Promise<import('./types').MediaItem | null> {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('caption', caption)
    try {
      const r = await sessionRequest('/api/media', { method: 'POST', body: fd })
      const j = await r.json()
      if (!r.ok) throw new Error(j.detail ?? `HTTP ${r.status}`)
      return j
    } catch (e: any) {
      this.toast(`Upload failed: ${e.message ?? e}`)
      return null
    }
  }
  savePositions(view: 'flow' | 'cab', positions: Record<string, { x: number; y: number }>) {
    return this.run(api('PUT', '/api/design/positions', { view, positions }))
  }
  analyze(id: string) {
    return api<import('./types').Analysis>('GET', `/api/equipment/${id}/analysis`)
  }

  // ---- A/B --------------------------------------------------------------------------
  setAB(slot: 'A' | 'B', snapshot: string | null) {
    return this.run(api('PUT', `/api/ab/${slot}`, { snapshot }))
  }
  toggleAB() {
    return this.run(api('POST', '/api/ab/toggle'))
  }

  async setSeat(seat: string) {
    this.seat = seat
    await this.refresh()
  }
}

export const app = new AppState()
