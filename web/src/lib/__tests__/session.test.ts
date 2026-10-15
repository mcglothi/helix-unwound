import { describe, expect, it, vi } from 'vitest'
import { consumeBootstrap, unlockSession } from '../session'

describe('owner session bootstrap', () => {
  it('removes the credential fragment while preserving path and query', () => {
    const replace = vi.fn()
    const token = consumeBootstrap({ hash: '#token=test%26credential', pathname: '/', search: '?view=studio' }, replace)
    expect(token).toBe('test&credential')
    expect(replace).toHaveBeenCalledExactlyOnceWith('/?view=studio')
  })
  it('leaves unrelated fragment navigation alone', () => {
    const replace = vi.fn()
    expect(consumeBootstrap({ hash: '#studio', pathname: '/', search: '' }, replace)).toBeNull()
    expect(replace).not.toHaveBeenCalled()
  })
  it('removes even an empty credential fragment', () => {
    const replace = vi.fn()
    expect(consumeBootstrap({ hash: '#token=', pathname: '/', search: '' }, replace)).toBe('')
    expect(replace).toHaveBeenCalledExactlyOnceWith('/')
  })
  it('exchanges the credential in a same-origin POST body', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}', { status: 200 }))
    await unlockSession('test-credential', request)
    expect(request).toHaveBeenCalledWith('/api/session', expect.objectContaining({
      method: 'POST', credentials: 'same-origin', body: JSON.stringify({ token: 'test-credential' }),
    }))
  })
  it('rejects failed authentication without including the credential in its error', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}', { status: 401 }))
    await expect(unlockSession('test-credential', request)).rejects.toThrow('The owner credential was not accepted.')
  })
})
