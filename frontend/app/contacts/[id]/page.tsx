'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet, apiPatch, apiDelete } from '@/lib/api'
import { ALL_ROLES, RequireRole, useUser } from '@/lib/rbac'
import {
  CONTACT_TYPE_LABELS, CONTACT_CASE_ROLE_LABELS,
  type ContactDetail, type ContactType,
} from '@/lib/types'

const TYPE_OPTIONS: ContactType[] = [
  'client', 'opposing_party', 'opposing_counsel',
  'court', 'judge', 'notary', 'government', 'expert', 'other',
]

export default function ContactDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { user } = useUser()
  const [contact, setContact] = useState<ContactDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<Partial<ContactDetail>>({})
  const [busy, setBusy] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const data = await apiGet<ContactDetail>(`/contacts/${id}`)
      setContact(data)
      setForm(data)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [id])

  async function onSave() {
    if (!form) return
    setBusy(true)
    setError(null)
    try {
      const updated = await apiPatch<ContactDetail>(`/contacts/${id}`, {
        type: form.type,
        name_ar: form.name_ar,
        name_en: form.name_en || null,
        national_id: form.national_id || null,
        tax_id: form.tax_id || null,
        phone: form.phone || null,
        email: form.email || null,
        address: form.address || null,
        notes: form.notes || null,
      })
      setContact(updated)
      setEditing(false)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    } finally {
      setBusy(false)
    }
  }

  async function onDeactivate() {
    if (!confirm('تأكيد إلغاء تفعيل جهة الاتصال؟')) return
    try {
      await apiDelete(`/contacts/${id}`)
      router.push('/contacts')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    }
  }

  const fieldCls = 'w-full rounded border border-gray-300 px-3 py-2 text-sm'

  if (loading) return <AppShell><p className="text-sm text-gray-500">جارٍ التحميل…</p></AppShell>
  if (!contact) return <AppShell><p className="text-sm text-red-600">{error}</p></AppShell>

  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <div className="mx-auto max-w-3xl">
          {/* Header */}
          <div className="flex items-start justify-between mb-6">
            <div>
              <h1 className="text-xl font-bold">{contact.name_ar}</h1>
              {contact.name_en && <p className="text-sm text-gray-500">{contact.name_en}</p>}
              <span className="mt-1 inline-block rounded-full bg-blue-50 px-3 py-0.5 text-xs text-blue-700">
                {CONTACT_TYPE_LABELS[contact.type]}
              </span>
              {!contact.is_active && (
                <span className="mr-2 inline-block rounded-full bg-gray-100 px-3 py-0.5 text-xs text-gray-500">
                  غير نشط
                </span>
              )}
            </div>
            <div className="flex gap-2">
              {!editing && (
                <button
                  onClick={() => setEditing(true)}
                  className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
                >
                  تعديل
                </button>
              )}
              {user?.role === 'partner_manager' && contact.is_active && (
                <button
                  onClick={onDeactivate}
                  className="rounded border border-red-200 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50"
                >
                  إلغاء التفعيل
                </button>
              )}
            </div>
          </div>

          {error && (
            <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>
          )}

          {editing ? (
            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-4 mb-6">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm font-medium">النوع</label>
                  <select
                    value={form.type}
                    onChange={e => setForm(f => ({ ...f, type: e.target.value as ContactType }))}
                    className={fieldCls}
                  >
                    {TYPE_OPTIONS.map(t => <option key={t} value={t}>{CONTACT_TYPE_LABELS[t]}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">الاسم بالعربية *</label>
                  <input value={form.name_ar ?? ''} onChange={e => setForm(f => ({ ...f, name_ar: e.target.value }))} className={fieldCls} required />
                </div>
                {(['name_en','national_id','tax_id','phone','email','address','notes'] as const).map(key => (
                  <div key={key} className={key === 'address' || key === 'notes' ? 'sm:col-span-2' : ''}>
                    <label className="mb-1 block text-sm font-medium">
                      {{ name_en: 'الاسم بالإنجليزية', national_id: 'رقم قومي', tax_id: 'رقم ضريبي', phone: 'هاتف', email: 'بريد', address: 'عنوان', notes: 'ملاحظات' }[key]}
                    </label>
                    {key === 'notes' ? (
                      <textarea value={(form[key] ?? '') as string} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} rows={3} className={fieldCls} />
                    ) : (
                      <input value={(form[key] ?? '') as string} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} className={fieldCls} dir={['national_id','tax_id','phone','email'].includes(key) ? 'ltr' : undefined} />
                    )}
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <button onClick={onSave} disabled={busy} className="rounded bg-blue-700 px-4 py-2 text-sm text-white hover:bg-blue-800 disabled:opacity-50">
                  {busy ? 'جارٍ الحفظ…' : 'حفظ'}
                </button>
                <button onClick={() => { setEditing(false); setForm(contact) }} className="rounded border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">
                  إلغاء
                </button>
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm mb-6">
              <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2 text-sm">
                {[
                  ['رقم قومي', contact.national_id],
                  ['رقم ضريبي', contact.tax_id],
                  ['هاتف', contact.phone],
                  ['بريد إلكتروني', contact.email],
                  ['عنوان', contact.address],
                  ['ملاحظات', contact.notes],
                ].map(([label, val]) => val ? (
                  <div key={label as string}>
                    <dt className="font-medium text-gray-500">{label as string}</dt>
                    <dd className="mt-0.5">{val as string}</dd>
                  </div>
                ) : null)}
              </dl>
            </div>
          )}

          {/* Linked cases */}
          <h2 className="text-base font-semibold mb-3">القضايا المرتبطة ({contact.cases.length})</h2>
          {contact.cases.length === 0 ? (
            <p className="text-sm text-gray-500">لا توجد قضايا مرتبطة</p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-right">
                  <tr>
                    <th className="px-4 py-2 font-semibold">القضية</th>
                    <th className="px-4 py-2 font-semibold">رقم القضية</th>
                    <th className="px-4 py-2 font-semibold">الدور</th>
                    <th className="px-4 py-2"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {contact.cases.map(cc => (
                    <tr key={cc.case_id} className="hover:bg-gray-50">
                      <td className="px-4 py-2">{cc.title}</td>
                      <td className="px-4 py-2 text-gray-500">{cc.case_number ?? '—'}</td>
                      <td className="px-4 py-2">
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs">
                          {CONTACT_CASE_ROLE_LABELS[cc.role]}
                        </span>
                      </td>
                      <td className="px-4 py-2">
                        <Link href={`/cases/${cc.case_id}`} className="text-blue-700 hover:underline">
                          عرض
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </AppShell>
    </RequireRole>
  )
}
