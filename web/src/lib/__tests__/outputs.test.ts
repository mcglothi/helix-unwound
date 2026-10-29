import { expect, it } from 'vitest'
import { routeLabel, setupChanges, setupMix } from '../outputs'
import type { Channel } from '../types'
const channel = { name: 'Door left', role: 'midbass', mix: { L: 0.25, R: 0.75 } } satisfies Pick<Channel, 'name' | 'role' | 'mix'>
it('preserves custom mix weights through an unrelated output-name edit', () => {
  const mix = setupMix('custom', channel.mix)
  expect(mix).toEqual(channel.mix)
  mix.L = 1
  expect(channel.mix.L).toBe(0.25)
  expect(setupChanges(channel, {name:'New name', role:'midbass', source:'custom'})).toEqual([
    {label:'Name', before:'Door left', after:'New name'},
  ])
})
it('reviews the exact route replacement instead of hiding a custom input mix', () => {
  expect(setupChanges(channel, {name:'Door left', role:'midbass', source:'mono'})).toEqual([
    {label:'Input route', before:'Custom · L × 0.25, R × 0.75', after:'Mono L+R'},
  ])
  expect(setupMix('off', channel.mix)).toEqual({})
  expect(routeLabel({L:0,R:0})).toBe('Off')
})
it('treats absent and explicit zero input weights as the same route', () => {
  expect(setupChanges({...channel,mix:{L:1,R:0}}, {name:'Door left',role:'midbass',source:'L'})).toEqual([])
})
