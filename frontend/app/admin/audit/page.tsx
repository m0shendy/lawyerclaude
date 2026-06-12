'use client'

// US5 audit log viewer (T029): filterable, paginated, field-level old→new diff,
// secret entries show action-only badge. Zero mutation affordances. [FR-311]

import { useEffect, useState } from 'react'
import { adminGet } from '@/lib/adminApi'

interface AuditLogItem {
  id: string
  firm_id: string | null
  actor_id: string | null
  actor_role: string | null
  context: string | null
  entity: string | null
  record_id: string | null
  action: string
  old_data: Record<string, unknown> | null
  new_data: Record<string, unknown> | null
  when_ts: string
}

const SECRET_ENTITIES = new Set(['credentials', 'api_keys', 'secrets', 'tokens'])

function DiffRow({ old_data, new_data }: { old_data: unknown; new_data: unknown }) {
  if (!old_data && !new_data) return null
  const allKeys = Array.from(new Set([
    ...Object.keys((old_data as Record<string, unknown>) ?? {}),
    ...Object.keys((new_data as Record<string, unknown>) ?? {}),
  ]))
  if (allKeys.length === 0) return null
  return (
    <table className="mt-2 w-full text-xs">
      <thead>
        <tr className="text-left text-gray-400">
          <th className="pr-3">حقل</th>
          <th className="pr-3">قبل</th>
          <th>بعد</th>
        </tr>
      </thead>
      <tbody>
        {allKeys.map((k) => {
          const before = (old_data as Record<string, unknown>)?.[k]
          const after = (new_data as Record<string, unknown>)?.[k]
          const changed = JSON.stringify(before) !== JSON.stringify(after)
          return (
            <tr key={k} className={changed ? 'bg-amber-50' : ''}>
              <td className="pr-3 font-mono">{k}</td>
              <td className="pr-3 text-red-600">{before != null ? String(before) : '—'}</td>
              <td className="text-green-600">{after != null ? String(after) : '—'}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export default function AdminAuditPage() {
  const [rows, setRows] = useState<AuditLogItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [page, setPage] = useState(0)

  const [filterFirmId, setFilterFirmId] = useState('')
  const [filterEntity, setFilterEntity] = useState('')
  const [filterAction, setFilterAction] = useState('')
  const [filterPlatformOnly, setFilterPlatformOnly] = useState(false)
  const [filterDateFrom, setFilterDateFrom] = useState('')
  const [filterDateTo, setFilterDateTo] = useState('')

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (filterFirmId) params.set('firm_id', filterFirmId)
      if (filterEntity) params.set('entity', filterEntity)
      if (filterAction) params.set('action', filterAction)
      if (filterPlatformOnly) params.set('platform_only', 'true')
      if (filterDateFrom) params.set('date_from', filterDateFrom)
      if (filterDateTo) params.set('date_to', filterDateTo)
      params.set('page', String(page))
      params.set('page_size', '50')
      const data = await adminGet<AuditLogItem[]>(`/admin/audit?${params}`)
      setRows(data)
    } catch {
      setError('فشل تحميل سجل التدقيق')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [page, filterFirmId, filterEntity, filterAction, filterPlatformOnly, filterDateFrom, filterDateTo])

  function toggleExpand(id: string) {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div dir="rtl">
      <h1 className="mb-4 text-xl font-bold">سجل التدقيق</h1>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap gap-2">
        <input type="text" placeholder="معرّف المكتب…" value={filterFirmId}
          onChange={e => { setFilterFirmId(e.target.value); setPage(0) }}
          className="rounded border border-gray-300 px-3 py-1 text-sm" />
        <input type="text" placeholder="الكيان…" value={filterEntity}
          onChange={e => { setFilterEntity(e.target.value); setPage(0) }}
          className="rounded border border-gray-300 px-3 py-1 text-sm" />
        <select value={filterAction} onChange={e => { setFilterAction(e.target.value); setPage(0) }}
          className="rounded border border-gray-300 px-2 py-1 text-sm">
          <option value="">الإجراء: الكل</option>
          <option value="create">إنشاء</option>
          <option value="update">تحديث</option>
          <option value="delete">حذف</option>
        </select>
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={filterPlatformOnly}
            onChange={e => { setFilterPlatformOnly(e.target.checked); setPage(0) }} />
          إجراءات المشغّل فقط
        </label>
        <input type="date" value={filterDateFrom}
          onChange={e => { setFilterDateFrom(e.target.value); setPage(0) }}
          className="rounded border border-gray-300 px-2 py-1 text-sm" />
        <span className="flex items-center text-sm text-gray-400">→</span>
        <input type="date" value={filterDateTo}
          onChange={e => { setFilterDateTo(e.target.value); setPage(0) }}
          className="rounded border border-gray-300 px-2 py-1 text-sm" />
      </div>

      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}

      {loading ? (
        <p className="text-sm text-gray-400">جارٍ التحميل…</p>
      ) : (
        <div className="rounded border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-gray-200 bg-gray-50 text-right">
              <tr>
                <th className="px-4 py-2 font-medium">الوقت</th>
                <th className="px-4 py-2 font-medium">الكيان</th>
                <th className="px-4 py-2 font-medium">الإجراء</th>
                <th className="px-4 py-2 font-medium">المنفّذ</th>
                <th className="px-4 py-2 font-medium">السياق</th>
                <th className="px-4 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const isSecret = r.entity ? SECRET_ENTITIES.has(r.entity) : false
                const isExpanded = expanded.has(r.id)
                return [
                  <tr key={r.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-2 text-xs text-gray-500 ltr">
                      {new Date(r.when_ts).toLocaleString('en-GB')}
                    </td>
                    <td className="px-4 py-2">{r.entity ?? '—'}</td>
                    <td className="px-4 py-2">
                      <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                        r.action === 'delete' ? 'bg-red-100 text-red-700' :
                        r.action === 'update' ? 'bg-amber-100 text-amber-700' :
                        'bg-blue-100 text-blue-700'
                      }`}>{r.action}</span>
                    </td>
                    <td className="px-4 py-2 text-xs text-gray-500 font-mono ltr">{r.actor_id?.slice(0, 8) ?? '—'}</td>
                    <td className="px-4 py-2 text-xs text-gray-500">{r.context ?? '—'}</td>
                    <td className="px-4 py-2 text-left">
                      {isSecret ? (
                        <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">🔑 action-only</span>
                      ) : (
                        <button
                          onClick={() => toggleExpand(r.id)}
                          className="text-xs text-blue-600 hover:underline"
                        >
                          {isExpanded ? 'إخفاء' : 'تفاصيل'}
                        </button>
                      )}
                    </td>
                  </tr>,
                  isExpanded && !isSecret ? (
                    <tr key={`${r.id}-detail`} className="bg-gray-50">
                      <td colSpan={6} className="px-4 py-2">
                        <DiffRow old_data={r.old_data} new_data={r.new_data} />
                      </td>
                    </tr>
                  ) : null,
                ]
              })}
              {rows.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-6 text-center text-gray-400">لا توجد سجلات</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      <div className="mt-3 flex gap-2 text-sm">
        <button disabled={page === 0} onClick={() => setPage(p => p - 1)}
          className="rounded border border-gray-300 px-3 py-1 disabled:opacity-40">السابق</button>
        <span className="flex items-center text-gray-500">صفحة {page + 1}</span>
        <button disabled={rows.length < 50} onClick={() => setPage(p => p + 1)}
          className="rounded border border-gray-300 px-3 py-1 disabled:opacity-40">التالي</button>
      </div>
    </div>
  )
}
