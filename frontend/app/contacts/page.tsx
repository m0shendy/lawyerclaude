'use client'

// Module A: Contacts & Parties list — searchable, filterable by type.

import { useEffect, useState, type FormEvent } from 'react'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet } from '@/lib/api'
import { ALL_ROLES, RequireRole } from '@/lib/rbac'
import { CONTACT_TYPE_LABELS, type Contact, type ContactType } from '@/lib/types'

const TYPE_OPTIONS: ContactType[] = [
  'client', 'opposing_party', 'opposing_counsel',
  'court', 'judge', 'notary', 'government', 'expert', 'other',
]

export default function ContactsPage() {
  const [contacts, setContacts] = useState<Contact[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<ContactType | ''>('')

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (search) params.set('search', search)
      if (typeFilter) params.set('type', typeFilter)
      const data = await apiGet<Contact[]>(`/contacts?${params}`)
      setContacts(data)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ غير متوقع')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [search, typeFilter])

  function onSearch(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    load()
  }

  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold">الأطراف والجهات</h1>
          <Link
            href="/contacts/new"
            className="rounded bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800"
          >
            + جهة جديدة
          </Link>
        </div>

        {/* Filters */}
        <form onSubmit={onSearch} className="mb-4 flex gap-3 flex-wrap">
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="بحث بالاسم أو الهاتف..."
            className="rounded border border-gray-300 px-3 py-2 text-sm flex-1 min-w-48"
          />
          <select
            value={typeFilter}
            onChange={e => setTypeFilter(e.target.value as ContactType | '')}
            className="rounded border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="">كل الأنواع</option>
            {TYPE_OPTIONS.map(t => (
              <option key={t} value={t}>{CONTACT_TYPE_LABELS[t]}</option>
            ))}
          </select>
        </form>

        {error && (
          <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>
        )}

        {loading ? (
          <p className="text-sm text-gray-500">جارٍ التحميل…</p>
        ) : contacts.length === 0 ? (
          <p className="text-sm text-gray-500">لا توجد جهات اتصال</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-right">
                <tr>
                  <th className="px-4 py-3 font-semibold">الاسم</th>
                  <th className="px-4 py-3 font-semibold">النوع</th>
                  <th className="px-4 py-3 font-semibold">الهاتف</th>
                  <th className="px-4 py-3 font-semibold">البريد</th>
                  <th className="px-4 py-3 font-semibold">الحالة</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {contacts.map(c => (
                  <tr key={c.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium">
                      {c.name_ar}
                      {c.name_en && <span className="mr-2 text-xs text-gray-400">{c.name_en}</span>}
                    </td>
                    <td className="px-4 py-3">
                      <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
                        {CONTACT_TYPE_LABELS[c.type]}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-600 dir-ltr">{c.phone ?? '—'}</td>
                    <td className="px-4 py-3 text-gray-600">{c.email ?? '—'}</td>
                    <td className="px-4 py-3">
                      {c.is_active ? (
                        <span className="text-green-700">نشط</span>
                      ) : (
                        <span className="text-gray-400">غير نشط</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Link href={`/contacts/${c.id}`} className="text-blue-700 hover:underline">
                        عرض
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </AppShell>
    </RequireRole>
  )
}
