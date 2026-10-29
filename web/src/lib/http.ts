import { sessionRequest } from './session'
export async function workstationRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await sessionRequest(path, { method,
    headers: body === undefined ? {} : { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body) })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail)
      ? data.detail.map((item: {msg?: string}) => item.msg ?? 'Check the supplied values').join('; ') : undefined
    throw new Error(data.problems?.join('; ') ?? detail ?? `Request failed (${response.status})`)
  }
  return data
}
