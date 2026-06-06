'use client'

import { useState, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import AppShell from '@/components/AppShell'
import { ApiError, apiPost } from '@/lib/api'
import { ALL_ROLES, RequireRole } from '@/lib/rbac'
import { CONTACT_TYPE_LABELS, type Contact, type ContactType } from '@/lib/types'

const TYPE_OPTIONS: ContactType[] = [
  'client', 'opposing_party', 'opposing_counsel',
  'court', 'judge', 'notary', 'government', 'expert', 'other',
]

export default function NewContactPage() {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({
    type: 'client' as ContactType,
    name_ar: '',
    name_en: '',
    national_id: '',
    tax_id: '',
    phone: '',
    email: '',
    address: '',
    notes: '',
  })

  const field = 'w-full rounded border border-gray-300 px-3 py-2 text-sm'

  function set(key: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
      setForm(f => ({ ...f, [key]: e.target.value }))
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const body: Record<string, string | null> = { type: form.type, name_ar: form.name_ar }
      if (form.name_en)     body.name_en     = form.name_en
      if (form.national_id) body.national_id = form.national_id
      if (form.tax_id)      body.tax_id      = form.tax_id
      if (form.phone)       body.phone       = form.phone
      if (form.email)       body.email       = form.email
      if (form.address)     body.address     = form.address
      if (form.notes)       body.notes       = form.notes

      const created = await apiPost<Contact>('/contacts', body)
      router.push(`/contacts/${created.id}`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ غير متوقع')
    } finally {
      setBusy(false)
    }
  }

  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <div className="mx-auto max-w-2xl">
          <h1 className="mb-6 text-xl font-bold">جهة اتصال جديدة</h1>

          {error && (
            <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>
          )}

          <form onSubmit={onSubmit} className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium">النوع *</label>
                <select value={form.type} onChange={set('type')} className={field} required>
                  {TYPE_OPTIONS.map(t => (
                    <option key={t} value={t}>{CONTACT_TYPE_LABELS[t]}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">الاسم بالعربية *</label>
                <input value={form.name_ar} onChange={set('name_ar')} className={field} required />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">الاسم بالإنجليزية</label>
                <input value={form.name_en} onChange={set('name_en')} className={field} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">رقم قومي</label>
                <input value={form.national_id} onChange={set('national_id')} className={field} dir="ltr" />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">رقم ضريبي</label>
                <input value={form.tax_id} onChange={set('tax_id')} className={field} dir="ltr" />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">هاتف</label>
                <input value={form.phone} onChange={set('phone')} className={field} dir="ltr" />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">بريد إلكتروني</label>
                <input type="email" value={form.email} onChange={set('email')} className={field} dir="ltr" />
              </div>
              <div className="sm:col-span-2">
                <label className="mb-1 block text-sm font-medium">العنوان</label>
                <input value={form.address} onChange={set('address')} className={field} />
              </div>
              <div className="sm:col-span-2">
                <label className="mb-1 block text-sm font-medium">ملاحظات</label>
                <textarea value={form.notes} onChange={set('notes')} rows={3} className={field} />
              </div>
            </div>

            <div className="flex gap-3 pt-2">
              <button
                type="submit"
                disabled={busy}
                className="rounded bg-blue-700 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
              >
                {busy ? 'جارٍ الحفظ…' : 'حفظ'}
              </button>
              <button
                type="button"
                onClick={() => router.back()}
                className="rounded border border-gray-300 px-5 py-2 text-sm hover:bg-gray-50"
              >
                إلغاء
              </button>
            </div>
          </form>
        </div>
      </AppShell>
    </RequireRole>
  )
}
