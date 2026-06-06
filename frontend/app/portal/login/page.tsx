'use client'

import { useState, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export default function PortalLoginPage() {
  const router = useRouter()
  const [step, setStep] = useState<'request' | 'verify'>('request')
  const [contact, setContact] = useState('')  // phone or email
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  async function onRequestLink(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/portal/auth/request-link`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ contact }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d.detail ?? 'حدث خطأ')
      }
      setInfo('تم إرسال رابط تسجيل الدخول إلى جهازك. أدخل الرمز الذي استلمته.')
      setStep('verify')
    } catch (e: any) {
      setError(e.message ?? 'حدث خطأ غير متوقع')
    } finally {
      setBusy(false)
    }
  }

  async function onVerify(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/portal/auth/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d.detail ?? 'رمز غير صالح أو منتهي الصلاحية')
      }
      const data = await res.json()
      // Store portal token in sessionStorage (not localStorage — clears on tab close)
      sessionStorage.setItem('portal_token', data.access_token)
      router.push('/portal/dashboard')
    } catch (e: any) {
      setError(e.message ?? 'حدث خطأ')
    } finally {
      setBusy(false)
    }
  }

  const inp = 'w-full rounded border border-gray-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500'

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4" dir="rtl">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-gray-900">بوابة العملاء</h1>
          <p className="mt-2 text-sm text-gray-500">تتبّع قضاياك ومستنداتك وفواتيرك</p>
        </div>

        <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
          {error && <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>}
          {info && <div className="mb-4 rounded bg-blue-50 px-4 py-2 text-sm text-blue-700">{info}</div>}

          {step === 'request' ? (
            <form onSubmit={onRequestLink} className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">رقم الجوال أو البريد الإلكتروني</label>
                <input
                  value={contact}
                  onChange={e => setContact(e.target.value)}
                  className={inp}
                  required
                  placeholder="+201234567890 أو email@example.com"
                  dir="ltr"
                />
              </div>
              <button
                type="submit"
                disabled={busy}
                className="w-full rounded-lg bg-blue-700 py-3 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
              >
                {busy ? 'جارٍ الإرسال…' : 'إرسال رابط الدخول'}
              </button>
            </form>
          ) : (
            <form onSubmit={onVerify} className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">رمز التحقق</label>
                <input
                  value={token}
                  onChange={e => setToken(e.target.value)}
                  className={`${inp} font-mono tracking-widest text-center text-lg`}
                  required
                  placeholder="أدخل الرمز هنا"
                  dir="ltr"
                  autoComplete="one-time-code"
                />
              </div>
              <button
                type="submit"
                disabled={busy}
                className="w-full rounded-lg bg-blue-700 py-3 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
              >
                {busy ? 'جارٍ التحقق…' : 'دخول'}
              </button>
              <button
                type="button"
                onClick={() => { setStep('request'); setToken(''); setInfo(null) }}
                className="w-full text-xs text-gray-500 hover:underline mt-1"
              >
                إعادة إرسال الرمز
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
