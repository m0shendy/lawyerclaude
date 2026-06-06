'use client'

// T041 — Audit log viewer. [C-III]
// Manager-only, strictly READ-ONLY: this screen offers no edit/delete
// affordances whatsoever — the audit_log is append-only at the DB level and
// this page only renders what GET /audit-log returns.

import { useCallback, useEffect, useState, Fragment } from 'react'
import AppShell from '@/components/AppShell'
import { RequireRole, MANAGER_ONLY } from '@/lib/rbac'
import { apiGet, ApiError } from '@/lib/api'
import type { AuditEntry } from '@/lib/types'

// Audited tables (every public table except audit_log itself).
const KNOWN_TABLES: { value: string; label: string }[] = [
  { value: 'cases', label: 'القضايا' },
  { value: 'case_assignments', label: 'إسناد القضايا' },
  { value: 'documents', label: 'المستندات' },
  { value: 'document_chunks', label: 'مقاطع المستندات' },
  { value: 'ai_outputs', label: 'مخرجات الذكاء الاصطناعي' },
  { value: 'deadlines', label: 'المواعيد' },
  { value: 'tasks', label: 'المهام' },
  { value: 'users', label: 'المستخدمون' },
  { value: 'firm_settings', label: 'إعدادات المكتب' },
  { value: 'notifications_log', label: 'سجل الإشعارات' },
  { value: 'reports_log', label: 'سجل التقارير' },
  { value: 'references_private', label: 'المراجع الخاصة' },
  { value: 'reference_chunks', label: 'مقاطع المراجع' },
]

const TABLE_LABELS: Record<string, string> = Object.fromEntries(
  KNOWN_TABLES.map((t) => [t.value, t.label]),
)

const ACTION_LABELS: Record<AuditEntry['action'], string> = {
  create: 'إنشاء',
  update: 'تعديل',
  delete: 'حذف',
}

const ACTION_BADGE_CLASSES: Record<AuditEntry['action'], string> = {
  create: 'bg-green-100 text-green-800',
  update: 'bg-blue-100 text-blue-800',
  delete: 'bg-red-100 text-red-800',
}

const ROLE_LABELS_LOOSE: Record<string, string> = {
  partner_manager: 'شريك / مدير',
  lawyer: 'محامٍ',
  paralegal: 'مساعد قانوني',
  secretary: 'سكرتير',
}

interface AuditLogResponse {
  entries: AuditEntry[]
  limit: number
  offset: number
}

function formatWhen(ts: string): string {
  try {
    return new Date(ts).toLocaleString('ar-EG', {
      dateStyle: 'medium',
      timeStyle: 'medium',
    })
  } catch {
    return ts
  }
}

/** Renders a single old/new value; [REDACTED] secrets shown gray italic. */
function ChangeValue({ value }: { value: unknown }) {
  if (value === '[REDACTED]') {
    return <span className="italic text-gray-400">[REDACTED]</span>
  }
  if (value === null || value === undefined) {
    return <span className="text-gray-400">—</span>
  }
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  return <span className="break-all" dir="auto">{text}</span>
}

/** Expanded row: change_detail as a field / old / new mini-table. */
function ChangeDetailTable({ detail }: { detail: AuditEntry['change_detail'] }) {
  if (!detail || Object.keys(detail).length === 0) {
    return <p className="px-4 py-3 text-sm text-gray-500">لا توجد تفاصيل تغيير مسجلة</p>
  }
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-gray-200 text-right text-xs text-gray-500">
          <th className="px-4 py-2 font-medium">الحقل</th>
          <th className="px-4 py-2 font-medium">القيمة السابقة</th>
          <th className="px-4 py-2 font-medium">القيمة الجديدة</th>
        </tr>
      </thead>
      <tbody>
        {Object.entries(detail).map(([field, change]) => (
          <tr key={field} className="border-b border-gray-100 last:border-0 align-top">
            <td className="px-4 py-2 font-mono text-xs" dir="ltr">
              {field}
            </td>
            <td className="px-4 py-2">
              <ChangeValue value={change?.old} />
            </td>
            <td className="px-4 py-2">
              <ChangeValue value={change?.new} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

const LIMIT_OPTIONS = [25, 50, 100, 200] as const

function AuditViewer() {
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [entityTable, setEntityTable] = useState('')
  const [limit, setLimit] = useState<number>(50)
  const [offset, setOffset] = useState(0)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setExpanded(new Set())
    try {
      const params = new URLSearchParams()
      if (entityTable) params.set('entity_table', entityTable)
      params.set('limit', String(limit))
      params.set('offset', String(offset))
      const res = await apiGet<AuditLogResponse>(`/audit-log?${params.toString()}`)
      setEntries(res.entries)
    } catch (err) {
      setEntries([])
      setError(err instanceof ApiError ? err.message : 'تعذّر تحميل سجل التدقيق')
    } finally {
      setLoading(false)
    }
  }, [entityTable, limit, offset])

  useEffect(() => {
    void load()
  }, [load])

  function toggleRow(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const page = Math.floor(offset / limit) + 1
  const hasNext = entries.length === limit

  return (
    <div>
      <h1 className="mb-1 text-2xl font-bold">سجل التدقيق</h1>
      <p className="mb-6 text-sm text-gray-500">
        سجل تغييرات للقراءة فقط — يُكتب تلقائيًا من قاعدة البيانات ولا يمكن تعديله أو حذفه.
      </p>

      {/* Filters (read-only viewing controls) */}
      <div className="mb-4 flex flex-wrap items-end gap-4 rounded-lg border border-gray-200 bg-white p-4">
        <div>
          <label htmlFor="entity-table" className="mb-1 block text-sm font-medium">
            الجدول
          </label>
          <select
            id="entity-table"
            value={entityTable}
            onChange={(e) => {
              setEntityTable(e.target.value)
              setOffset(0)
            }}
            className="rounded border border-gray-300 bg-white px-3 py-2 text-sm"
          >
            <option value="">كل الجداول</option>
            {KNOWN_TABLES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label} ({t.value})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="limit" className="mb-1 block text-sm font-medium">
            عدد السجلات
          </label>
          <select
            id="limit"
            value={limit}
            onChange={(e) => {
              setLimit(Number(e.target.value))
              setOffset(0)
            }}
            className="rounded border border-gray-300 bg-white px-3 py-2 text-sm"
          >
            {LIMIT_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>

        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="rounded bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
        >
          تحديث
        </button>
      </div>

      {error && (
        <p className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {loading ? (
        <p className="p-8 text-center text-gray-500">جارٍ التحميل…</p>
      ) : entries.length === 0 && !error ? (
        <p className="rounded-lg border border-gray-200 bg-white p-8 text-center text-gray-500">
          لا توجد سجلات مطابقة
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50 text-right text-xs text-gray-600">
                <th className="px-4 py-3 font-medium">التاريخ والوقت</th>
                <th className="px-4 py-3 font-medium">الدور</th>
                <th className="px-4 py-3 font-medium">الجدول</th>
                <th className="px-4 py-3 font-medium">العملية</th>
                <th className="px-4 py-3 font-medium">السياق</th>
                <th className="px-4 py-3 font-medium">التفاصيل</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => {
                const isOpen = expanded.has(entry.id)
                return (
                  <Fragment key={entry.id}>
                    <tr
                      onClick={() => toggleRow(entry.id)}
                      className="cursor-pointer border-b border-gray-100 last:border-0 hover:bg-gray-50"
                    >
                      <td className="whitespace-nowrap px-4 py-3">{formatWhen(entry.when_ts)}</td>
                      <td className="whitespace-nowrap px-4 py-3">
                        {entry.who_role
                          ? ROLE_LABELS_LOOSE[entry.who_role] ?? entry.who_role
                          : '—'}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span title={entry.entity_table}>
                          {TABLE_LABELS[entry.entity_table] ?? entry.entity_table}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span
                          className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${ACTION_BADGE_CLASSES[entry.action]}`}
                        >
                          {ACTION_LABELS[entry.action]}
                        </span>
                      </td>
                      <td className="max-w-xs truncate px-4 py-3 text-gray-600">
                        {entry.context ?? '—'}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-blue-700">
                        {isOpen ? 'إخفاء التفاصيل ▲' : 'عرض التفاصيل ▼'}
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="border-b border-gray-100 bg-gray-50 last:border-0">
                        <td colSpan={6} className="p-0">
                          <ChangeDetailTable detail={entry.change_detail} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          onClick={() => setOffset(Math.max(0, offset - limit))}
          disabled={loading || offset === 0}
          className="rounded border border-gray-300 bg-white px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-50"
        >
          السابق
        </button>
        <span className="text-sm text-gray-600">صفحة {page.toLocaleString('ar-EG')}</span>
        <button
          type="button"
          onClick={() => setOffset(offset + limit)}
          disabled={loading || !hasNext}
          className="rounded border border-gray-300 bg-white px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-50"
        >
          التالي
        </button>
      </div>
    </div>
  )
}

export default function AuditPage() {
  return (
    <RequireRole roles={MANAGER_ONLY}>
      <AppShell>
        <AuditViewer />
      </AppShell>
    </RequireRole>
  )
}
