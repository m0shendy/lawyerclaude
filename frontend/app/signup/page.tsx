'use client'

// Public firm signup (WP-S3). [C-I v2]
// Creates: firm → manager credential → trial subscription, via POST /signup.
// Unauthenticated by design — the ONLY public write path in the product.

import { useState, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'

function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
}

export default function SignupPage() {
  const router = useRouter()
  const [firmName, setFirmName] = useState('')
  const [managerName, setManagerName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<{ trial_ends_at: string } | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (password.length < 10) {
      setError('كلمة المرور يجب ألا تقل عن 10 أحرف')
      return
    }
    setBusy(true)
    try {
      const res = await fetch(`${apiBase()}/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          firm_name: firmName,
          manager_name: managerName,
          email,
          phone: phone || null,
          password,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(body?.detail?.message ?? body?.message ?? 'فشل إنشاء الحساب')
      }
      setDone(await res.json())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'فشل إنشاء الحساب — حاول مرة أخرى')
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-100" dir="rtl">
        <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-8 text-center shadow-sm">
          <h1 className="mb-3 text-xl font-bold text-gray-900">تم إنشاء مكتبكم بنجاح 🎉</h1>
          <p className="mb-2 text-sm text-gray-600">
            الفترة التجريبية المجانية (14 يومًا) تنتهي في{' '}
            {new Date(done.trial_ends_at).toLocaleDateString('ar-EG')}
          </p>
          <p className="mb-6 text-sm text-gray-600">يمكنكم الآن تسجيل الدخول بالبريد وكلمة المرور.</p>
          <button
            onClick={() => router.replace('/login')}
            className="w-full rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800"
          >
            تسجيل الدخول
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-100" dir="rtl">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-8 shadow-sm"
      >
        <h1 className="mb-1 text-xl font-bold text-gray-900">إنشاء حساب مكتب جديد</h1>
        <p className="mb-6 text-sm text-gray-500">
          14 يومًا تجربة مجانية — لا حاجة لبطاقة دفع. أداة مساعدة للمحامي، والمراجعة البشرية شرط لكل
          مخرجات الذكاء الاصطناعي.
        </p>

        <label className="mb-1 block text-sm font-medium text-gray-700">اسم المكتب</label>
        <input
          value={firmName}
          onChange={(e) => setFirmName(e.target.value)}
          required
          minLength={2}
          className="mb-4 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          placeholder="مكتب الشندي للمحاماة"
        />

        <label className="mb-1 block text-sm font-medium text-gray-700">اسم المدير المسؤول</label>
        <input
          value={managerName}
          onChange={(e) => setManagerName(e.target.value)}
          required
          minLength={2}
          className="mb-4 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />

        <label className="mb-1 block text-sm font-medium text-gray-700">البريد الإلكتروني</label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          dir="ltr"
          className="mb-4 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />

        <label className="mb-1 block text-sm font-medium text-gray-700">
          رقم الهاتف (واتساب) — اختياري
        </label>
        <input
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          dir="ltr"
          className="mb-4 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          placeholder="+201XXXXXXXXX"
        />

        <label className="mb-1 block text-sm font-medium text-gray-700">كلمة المرور</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={10}
          dir="ltr"
          className="mb-6 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />

        {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
        >
          {busy ? 'جارٍ الإنشاء…' : 'إنشاء المكتب وبدء التجربة المجانية'}
        </button>

        <p className="mt-4 text-center text-xs text-gray-500">
          بإنشاء الحساب فأنتم توافقون على شروط الاستخدام — تبقى مسؤولية المواعيد والقرارات القانونية
          على المحامي.
        </p>
      </form>
    </div>
  )
}
