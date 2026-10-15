import { afterEach, describe, expect, it, vi } from 'vitest'
import { app } from '../state.svelte'
import { canApply } from '../proposal'
import type { Proposal } from '../types'

const proposal: Proposal = {
  id: 'p1', kind: 'auto_eq', title: 'EQ to target (C)', notes: [], source: 'agent', metrics: {},
  edits: [{ channel: 'C', field: 'eq', label: 'C: 1 band' }],
}
const CONFLICTS = ['channel C processing (role/filters/EQ/level/mute/routing) changed since this proposal']

function server(applyStatus: number) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
    if (url.endsWith('/apply') && init?.method === 'POST')
      return applyStatus === 409 ? json({ error: 'conflict', conflicts: CONFLICTS }, 409) : json({ ok: true })
    if (url.includes('/preview')) return applyStatus === 409 ? json({ error: 'conflict', conflicts: CONFLICTS }, 409) : json({})
    if (url === '/api/status')
      return json({ revision: 1, proposals: applyStatus === 409 ? [{ id: 'p1' }] : [], device: {}, ab: {}, recent_events: [] })
    if (url === '/api/snapshots') return json([])
    return json({})
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  app.closeProposal()
})

describe('applying a proposal', () => {
  it('keeps the proposal open with reasons when the engine returns 409, and disables apply', async () => {
    vi.stubGlobal('fetch', server(409))
    app.proposal = proposal
    const ok = await app.applyProposal()
    expect(ok).toBe(false)
    expect(app.proposal?.id).toBe('p1')
    expect(app.proposalConflicts).toEqual(CONFLICTS)
    expect(canApply(app.proposal, app.proposalConflicts)).toBe(false)
  })

  it('closes the proposal only after the engine accepts it', async () => {
    vi.stubGlobal('fetch', server(200))
    app.proposal = proposal
    const ok = await app.applyProposal()
    expect(ok).toBe(true)
    expect(app.proposal).toBeNull()
  })

  it('cannot apply an empty proposal', () => {
    expect(canApply({ ...proposal, edits: [] }, [])).toBe(false)
    expect(canApply(proposal, [])).toBe(true)
  })
})
