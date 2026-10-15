/** Remove bootstrap credentials from the address bar before making requests. */
export function consumeBootstrap(
  location: Pick<Location, 'hash' | 'pathname' | 'search'>,
  replace: (url: string) => void,
): string | null {
  const token = new URLSearchParams(location.hash.slice(1)).get('token')
  if (token !== null) replace(location.pathname + location.search)
  return token
}

export async function unlockSession(token: string, request: typeof fetch = fetch): Promise<void> {
  const response = await request('/api/session', {
    method: 'POST', credentials: 'same-origin', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ token }),
  })
  if (!response.ok) throw new Error('The owner credential was not accepted.')
}

export const SESSION_ENDED = 'helixtune:session-ended'

/** Notify the gate on lost authentication; transport errors keep the offline view. */
export async function sessionRequest(
  input: RequestInfo | URL, init?: RequestInit,
  request: typeof fetch = fetch,
  ended: () => void = () => window.dispatchEvent(new Event(SESSION_ENDED)),
): Promise<Response> {
  const response = await request(input, init)
  if (response.status === 401) ended()
  return response
}
