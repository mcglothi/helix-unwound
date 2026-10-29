import { expect, it } from 'vitest'
import { adjacentOutput, shortcutFor } from '../shortcuts'
const key = { key:'z', metaKey:true, ctrlKey:false, altKey:false, shiftKey:false, repeat:false }
it('keeps native editing and open dialogs in charge of their keyboard events', () => {
  expect(shortcutFor(key,true,false)).toBeNull()
  expect(shortcutFor(key,false,true)).toBeNull()
  expect(shortcutFor({...key,repeat:true},false,false)).toBeNull()
  expect(shortcutFor({...key,altKey:true},false,false)).toBeNull()
})
it('recognises Mac and Windows history commands without hijacking unrelated commands', () => {
  expect(shortcutFor(key,false,false)).toBe('undo')
  expect(shortcutFor({...key,shiftKey:true},false,false)).toBe('redo')
  expect(shortcutFor({...key,key:'y',metaKey:false,ctrlKey:true},false,false)).toBe('redo')
  expect(shortcutFor({...key,key:'y'},false,false)).toBeNull()
  expect(shortcutFor({...key,key:'r'},false,false)).toBeNull()
})
it('supports output navigation without a modifier and wraps across physical sockets', () => {
  expect(shortcutFor({...key,key:']',metaKey:false},false,false)).toBe('next-output')
  expect(shortcutFor({...key,key:']'},false,false)).toBeNull()
  expect(adjacentOutput(['A','B','J'],'J',1)).toBe('A')
  expect(adjacentOutput(['A','B','J'],'A',-1)).toBe('J')
  expect(adjacentOutput([],'A',1)).toBe('A')
})
