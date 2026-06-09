'use client'

// Portal profile — client views and edits contact fields (spec 002 US9, T078).
// PATCH /portal/profile is audit-logged on the backend [C-III].

import { useEffect, useState, type FormEvent } from 'react'

const BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api'

interface PortalProfile {
  id: string
  name: string
  phone: string | null
  email: string | null
  address: string | null
}

export default function PortalProfilePage() {
  const [profile, setProfile] = useState<PortalProfile | null>(null)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [address, setAddress] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)

  const token = () => sessionStorage.getItem('portal_token') ?? localStorage.getItem('portal_token') ?? ''

  useEffect(() => {
    fetch(`${BASE}/portal/profile`, { headers: { Authorization: `Bearer ${token()}` } })
      .then(r => r.json() as Promise<PortalProfile>)
      .then(p => {
        setProfile(p)
        setName(p.name ?? '')
        setPhone(p.phone ?? '')
        setEmail(p.email ?? '')
        setAddress(p.address ?? '')
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  async function save(e: FormEvent) {
    e.preventDefault()
    setSaving(true); setMsg(null)
    try {
      const res = await fetch(`${BASE}/portal/profile`, {
        method: 'PATCH',
        headers: {
          Authorization: `Bearer ${token()}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name, phone: phone || null, email: email || null, address: address || null }),
      })
      if (!res.ok) {
        const b = await res.json().catch(() => ({})) as Record<string, unknown>
        throw new Error((b?.error as Record<string, unknown>)?.message as string ?? `خطأ ${res.status}`)
      }
      const updated = await res.json() as PortalProfile
      setProfile(updated)
      setMsg({ type: 'ok', text: 'تم تحديث البيانات بنجاح ✓' })
    } catch (e) {
      setMsg({ type: 'err', text: e instanceof Error ? e.message : 'تعذّر الحفظ' })
    } finally { setSaving(false) }
  }

  if (loading) return <p className="text-sm text-gray-400">جارٍ التحميل…</p>

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold">حسابي</h2>

      <form onSubmit={save} className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-4">
        <label className="block text-sm">
          الاسم الكامل *
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            required
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </label>

        <label className="block text-sm">
          رقم الهاتف
          <input
            type="tel"
            value={phone}
            onChange={e => setPhone(e.target.value)}
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            dir="ltr"
          />
        </label>

        <label className="block text-sm">
          البريد الإلكتروني
          <input
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            dir="ltr"
          />
        </label>

        <label className="block text-sm">
          العنوان
          <textarea
            value={address}
            onChange={e => setAddress(e.target.value)}
            rows={3}
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </label>

        {msg && (
          <div className={`rounded px-3 py-2 text-sm ${msg.type === 'ok' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
            {msg.text}
          </div>
        )}

        <button
          type="submit"
          disabled={saving}
          className="w-full rounded-lg bg-blue-700 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
        >
          {saving ? 'جارٍ الحفظ…' : 'حفظ التعديلات'}
        </button>
      </form>
    </div>
  )
}
