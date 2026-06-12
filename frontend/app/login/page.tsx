'use client'

// Login screen (T030). Per-instance users only — this frontend talks to ITS
// firm's Supabase stack alone; a user from another firm cannot authenticate
// here because they don't exist in this instance's GoTrue. [C-I]

import { useState, type FormEvent } from 'react'

import { signInWithPassword } from '@/lib/supabase'
import { useUser } from '@/lib/rbac'

export default function LoginPage() {
  const { refresh } = useUser()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await signInWithPassword(email, password)
      const user = await refresh() // /me also rejects inactive users
      if (!user) throw new Error('Inactive user')
      window.location.href = '/dashboard'
    } catch {
      setError('بيانات الدخول غير صحيحة أو الحساب موقوف')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-100">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm rounded-xl border border-gray-200 bg-white p-8 shadow-sm"
      >
        <h1 className="mb-6 text-center text-xl font-bold">تسجيل الدخول</h1>

        <label className="mb-1 block text-sm font-medium" htmlFor="email">
          البريد الإلكتروني
        </label>
        <input
          id="email"
          type="email"
          dir="ltr"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mb-4 w-full rounded border border-gray-300 px-3 py-2 text-left"
        />

        <label className="mb-1 block text-sm font-medium" htmlFor="password">
          كلمة المرور
        </label>
        <input
          id="password"
          type="password"
          dir="ltr"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mb-4 w-full rounded border border-gray-300 px-3 py-2 text-left"
        />

        {error && <p className="mb-4 text-sm text-red-700">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded bg-blue-700 py-2 font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
        >
          {busy ? 'جارٍ الدخول…' : 'دخول'}
        </button>
      </form>
    </div>
  )
}
