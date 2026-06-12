/**
 * Fetch wrapper for /admin/* endpoints.
 *
 * Stores the operator access token in sessionStorage (not localStorage — clears
 * on tab close) so a refreshed tab forces re-authentication without polluting
 * other tabs.  Any 401 from any /admin/* call clears the token and redirects to
 * /admin/login with an "انتهت الجلسة" notice.
 */

const TOKEN_KEY = 'operator_access_token'
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ''

export function getOperatorToken(): string | null {
  if (typeof window === 'undefined') return null
  return sessionStorage.getItem(TOKEN_KEY)
}

export function setOperatorToken(token: string): void {
  if (typeof window === 'undefined') return
  sessionStorage.setItem(TOKEN_KEY, token)
}

export function clearOperatorToken(): void {
  if (typeof window === 'undefined') return
  sessionStorage.removeItem(TOKEN_KEY)
}

export async function adminFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const token = getOperatorToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers })

  if (res.status === 401) {
    clearOperatorToken()
    const url = new URL('/admin/login', window.location.origin)
    url.searchParams.set('notice', 'انتهت الجلسة')
    window.location.href = url.toString()
    // Return the 401 response anyway so callers that already catch can handle it
  }

  return res
}

/** Convenience: fetch + parse JSON; throws ApiError on non-2xx. */
export async function adminGet<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await adminFetch(path, init)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw Object.assign(new Error(body?.error?.message ?? res.statusText), {
      status: res.status,
      code: body?.error?.code,
    })
  }
  return res.json() as Promise<T>
}

/** POST helper with JSON body. */
export async function adminPost<T = unknown>(
  path: string,
  body?: unknown,
): Promise<T> {
  return adminGet<T>(path, {
    method: 'POST',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
}
