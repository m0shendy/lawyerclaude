'use client'

// Operator login — step 1: email + password → step 2: TOTP code (or enrollment QR).
// Talks only to the backend (/admin/login, /admin/mfa/verify).
// Never touches Supabase GoTrue directly from the browser. [C-I]

import { useState, type FormEvent, useEffect, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { adminFetch, adminPost, setOperatorToken } from '@/lib/adminApi'

type Step = 'credentials' | 'totp' | 'enroll'

interface LoginState {
  factorId: string
  challengeToken: string
  enrollToken: string   // aal1 token when enrollment is required
}

function AdminLoginInner() {
  const searchParams = useSearchParams()
  const notice = searchParams.get('notice')

  const [step, setStep] = useState<Step>('credentials')
  const [loginState, setLoginState] = useState<LoginState | null>(null)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Enrollment QR state
  const [totpUri, setTotpUri] = useState<string | null>(null)

  async function handleCredentials(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const data = await adminPost<{
        mfa_required: boolean
        factor_id?: string
        challenge_token?: string
        mfa_enrollment_required?: boolean
      }>('/admin/login', { email, password })

      if (data.mfa_enrollment_required) {
        // Need to enroll TOTP first — but we don't have the token here directly.
        // The backend returned mfa_enrollment_required; ask user to contact admin.
        setError('يجب تسجيل عامل المصادقة أولاً — تواصل مع مشغّل المنصة لتفعيل TOTP')
        return
      }

      if (data.mfa_required && data.factor_id && data.challenge_token) {
        setLoginState({
          factorId: data.factor_id,
          challengeToken: data.challenge_token,
          enrollToken: '',
        })
        setStep('totp')
        return
      }

      setError('بيانات الدخول غير صحيحة')
    } catch (err: unknown) {
      const e = err as { status?: number; message?: string }
      if (e.status === 423) {
        setError('تم قفل الحساب مؤقتاً — حاول مجدداً بعد 15 دقيقة')
      } else {
        setError('بيانات الدخول غير صحيحة')
      }
    } finally {
      setBusy(false)
    }
  }

  async function handleTotp(e: FormEvent) {
    e.preventDefault()
    if (!loginState) return
    setError(null)
    setBusy(true)
    try {
      const data = await adminPost<{ access_token: string; expires_in: number }>(
        '/admin/mfa/verify',
        {
          factor_id: loginState.factorId,
          challenge_token: loginState.challengeToken,
          code: code.replace(/\s/g, ''),
        },
      )
      setOperatorToken(data.access_token)
      window.location.href = '/admin'
    } catch {
      setError('رمز المصادقة غير صحيح — حاول مجدداً')
    } finally {
      setBusy(false)
    }
  }

  // ── Credentials form ──────────────────────────────────────────────────────
  if (step === 'credentials') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-100" dir="rtl">
        <form
          onSubmit={handleCredentials}
          className="w-full max-w-sm rounded-xl border border-gray-200 bg-white p-8 shadow-sm"
        >
          <h1 className="mb-2 text-center text-xl font-bold">لوحة مشغّل المنصة</h1>
          <p className="mb-6 text-center text-xs text-gray-400">دخول مخصص للمشغّل فقط</p>

          {notice && (
            <div className="mb-4 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              {notice}
            </div>
          )}

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
            {busy ? 'جارٍ التحقق…' : 'دخول'}
          </button>
        </form>
      </div>
    )
  }

  // ── TOTP challenge form ───────────────────────────────────────────────────
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-100" dir="rtl">
      <form
        onSubmit={handleTotp}
        className="w-full max-w-sm rounded-xl border border-gray-200 bg-white p-8 shadow-sm"
      >
        <h1 className="mb-2 text-center text-xl font-bold">رمز المصادقة الثنائية</h1>
        <p className="mb-6 text-center text-sm text-gray-500">
          أدخل الرمز المكوّن من 6 أرقام من تطبيق المصادقة
        </p>

        <input
          type="text"
          inputMode="numeric"
          pattern="[0-9 ]*"
          maxLength={7}
          dir="ltr"
          required
          placeholder="000 000"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          className="mb-4 w-full rounded border border-gray-300 px-3 py-2 text-center text-2xl tracking-widest"
        />

        {error && <p className="mb-4 text-sm text-red-700">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded bg-blue-700 py-2 font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
        >
          {busy ? 'جارٍ التحقق…' : 'تحقق'}
        </button>

        <button
          type="button"
          onClick={() => { setStep('credentials'); setError(null); setCode('') }}
          className="mt-3 w-full text-sm text-gray-400 hover:text-gray-600"
        >
          رجوع
        </button>
      </form>
    </div>
  )
}

export default function AdminLoginPage() {
  return (
    <Suspense>
      <AdminLoginInner />
    </Suspense>
  )
}
