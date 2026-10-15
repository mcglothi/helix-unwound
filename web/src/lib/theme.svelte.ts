// Theme selection is per device (localStorage); custom schemes are shared via the engine.

import { applyScheme, BUILTIN, type Scheme } from './themes'

const store = {
  get(k: string): string | null {
    try { return localStorage.getItem(k) } catch { return null }
  },
  set(k: string, v: string) {
    try { localStorage.setItem(k, v) } catch { /* private mode etc. */ }
  },
}

class ThemeState {
  custom = $state<Scheme[]>([])
  name = $state(store.get('helixtune.theme') ?? 'Studio')
  driveName = $state(store.get('helixtune.driveTheme') ?? '') // '' = same as app
  followSystem = $state(store.get('helixtune.followSystem') === '1')
  private mode: string = 'studio'
  private mq = typeof matchMedia === 'function' ? matchMedia('(prefers-color-scheme: light)') : null

  get all(): Scheme[] {
    return [...BUILTIN, ...this.custom]
  }

  find(name: string): Scheme {
    return this.all.find((t) => t.name === name) ?? BUILTIN[0]
  }

  async load() {
    try {
      const r = await fetch('/api/themes')
      if (r.ok) this.custom = await r.json()
    } catch { /* offline: builtins only */ }
    this.mq?.addEventListener('change', () => this.apply())
    this.apply()
  }

  apply(mode = this.mode) {
    this.mode = mode
    let sc = this.find(this.name)
    if (this.followSystem) sc = this.find(this.mq?.matches ? 'Studio Light' : 'Studio')
    if (mode === 'drive' && this.driveName) sc = this.find(this.driveName)
    applyScheme(sc)
  }

  choose(name: string) {
    this.name = name
    this.followSystem = false
    store.set('helixtune.theme', name)
    store.set('helixtune.followSystem', '0')
    this.apply()
  }
  chooseDrive(name: string) {
    this.driveName = name
    store.set('helixtune.driveTheme', name)
    this.apply()
  }
  setFollowSystem(on: boolean) {
    this.followSystem = on
    store.set('helixtune.followSystem', on ? '1' : '0')
    this.apply()
  }

  async save(sc: Scheme) {
    const r = await fetch('/api/themes', {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ...sc, builtin: undefined }),
    })
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `HTTP ${r.status}`)
    this.custom = [...this.custom.filter((t) => t.name !== sc.name), sc]
  }
  async remove(name: string) {
    await fetch(`/api/themes/${encodeURIComponent(name)}`, { method: 'DELETE' })
    this.custom = this.custom.filter((t) => t.name !== name)
    if (this.name === name) this.choose('Studio')
  }
}

export const theme = new ThemeState()
