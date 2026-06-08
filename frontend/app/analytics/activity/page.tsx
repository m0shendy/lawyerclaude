'use client'

// Activity feed — recent audit-log entries across the system.
// GET /audit-log?entity_table=&limit=&offset=
// Manager-only (RequireRole enforced); audit log is append-only [C-III].

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet } from '@/lib/api'
import { RequireRole } from '@/lib/rbac'

interface AuditEntry {
  id: string
  entity_table: string
  record_id: string
  action: string           // insert | update | delete
  changed_by: string | null
  changed_at: string
  changes: Record<string, unknown> | null
}

const ACTION_COLORS: Record<string, string> = {
  insert: 'bg-green-50 text-green-700',
  update: 'bg-blue-50 text-blue-700',
  delete: 'bg-red-50 text-red-700',
}

const ACTION_AR: Record<string, string> = {
  insert: 'إنشاء',
  update: 'تعديل',
  delete: 'حذف',
}

const TABLE_AR: Record<string, string> = {
  cases: 'قضية',
  contacts: 'جهة اتصال',
  hearings: 'جلسة',
  appointments: 'موعد',
  tasks: 'مهمة',
  invoices: 'فاتورة',
  documents: 'مستند',
  users: 'مستخدم',
  payments: 'دفعة',
  firm_settings: 'إعدادات',
}

const PAGE_SIZE = 50

export default function ActivityFeedPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [tableFilter, setTableFilter] = useState('')
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (newOffset: number, table: string) => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(newOffset) })
      if (table) params.set('entity_table', table)
      const data = await apiGet<AuditEntry[]>(`/audit-log?${params}`)
      setEntries(data)
      setHasMore(data.length === PAGE_SIZE)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    setOffset(0)
    load(0, tableFilter)
  }, [tableFilter, load])

  function prev() {
    const newOffset = Math.max(0, offset - PAGE_SIZE)
    setOffset(newOffset)
    load(newOffset, tableFilter)
  }

  function next() {
    const newOffset = offset + PAGE_SIZE
    setOffset(newOffset)
    load(newOffset, tableFilter)
  }

  return (
    <RequireRole roles={['partner_manager']}>
      <AppShell>
        <div className="mb-6 flex items-center gap-3">
          <Link href="/analytics" className="text-sm text-gray-500 hover:text-gray-700">
            ← التقارير
          </Link>
          <span className="text-gray-300">/</span>
          <h1 className="text-xl font-bold">سجل النشاطات</h1>
        </div>

        {/* Filters */}
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <select
            value={tableFilter}
            onChange={e => setTableFilter(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option value="">كل الجداول</option>
            {Object.entries(TABLE_AR).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
          <span className="text-xs text-gray-400">
            السجل للقراءة فقط — لا يمكن تعديله أو حذفه
          </span>
        </div>

        {error && (
          <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>
        )}

        {loading ? (
          <p className="py-8 text-center text-sm text-gray-500">جارٍ التحميل…</p>
        ) : entries.length === 0 ? (
          <p className="py-8 text-center text-sm text-gray-500">لا توجد سجلات</p>
        ) : (
          <>
            <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-right text-xs text-gray-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">الوقت</th>
                    <th className="px-4 py-3 font-medium">الجدول</th>
                    <th className="px-4 py-3 font-medium">الإجراء</th>
                    <th className="px-4 py-3 font-medium">السجل</th>
                    <th className="px-4 py-3 font-medium">المستخدم</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {entries.map(e => (
                    <tr key={e.id} className="hover:bg-gray-50">
                      <td className="px-4 py-2.5 whitespace-nowrap text-xs text-gray-500">
                        {new Date(e.changed_at).toLocaleString('ar-EG', {
                          year: 'numeric', month: '2-digit', day: '2-digit',
                          hour: '2-digit', minute: '2-digit',
                        })}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className="text-xs font-medium text-gray-700">
                          {TABLE_AR[e.entity_table] ?? e.entity_table}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${ACTION_COLORS[e.action] ?? 'bg-gray-100 text-gray-600'}`}>
                          {ACTION_AR[e.action] ?? e.action}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-400 max-w-[140px] truncate">
                        {e.record_id.slice(0, 8)}…
                      </td>
                      <td className="px-4 py-2.5 text-xs text-gray-600">
                        {e.changed_by ? e.changed_by.slice(0, 8) + '…' : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="mt-4 flex items-center justify-between text-sm">
              <button
                onClick={prev}
                disabled={offset === 0}
                className="rounded-lg border border-gray-300 px-3 py-1.5 text-gray-700 hover:bg-gray-50 disabled:opacity-40"
              >
                ← السابق
              </button>
              <span className="text-xs text-gray-500">
                {offset + 1}–{offset + entries.length}
              </span>
              <button
                onClick={next}
                disabled={!hasMore}
                className="rounded-lg border border-gray-300 px-3 py-1.5 text-gray-700 hover:bg-gray-50 disabled:opacity-40"
              >
                التالي →
              </button>
            </div>
          </>
        )}
      </AppShell>
    </RequireRole>
  )
}
