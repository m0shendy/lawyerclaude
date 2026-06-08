'use client'

// Operational report — workload distribution per lawyer.
// GET /reports/workload  →  open tasks, upcoming hearings, pending deadlines
// Manager-only (RequireRole enforced).

import { useEffect, useState } from 'react'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet } from '@/lib/api'
import { RequireRole } from '@/lib/rbac'

interface WorkloadRow {
  user_id: string
  user_name: string
  open_tasks: number
  upcoming_hearings: number
  pending_deadlines: number
}

export default function OperationalReportPage() {
  const [rows, setRows] = useState<WorkloadRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiGet<WorkloadRow[]>('/reports/workload')
      .then(setRows)
      .catch(e => setError(e instanceof ApiError ? e.message : 'حدث خطأ'))
      .finally(() => setLoading(false))
  }, [])

  const totalTasks = rows.reduce((s, r) => s + r.open_tasks, 0)
  const totalHearings = rows.reduce((s, r) => s + r.upcoming_hearings, 0)
  const totalDeadlines = rows.reduce((s, r) => s + r.pending_deadlines, 0)

  return (
    <RequireRole roles={['partner_manager']}>
      <AppShell>
        <div className="mb-6 flex items-center gap-3">
          <Link href="/analytics" className="text-sm text-gray-500 hover:text-gray-700">
            ← التقارير
          </Link>
          <span className="text-gray-300">/</span>
          <h1 className="text-xl font-bold">التقرير التشغيلي</h1>
        </div>

        {error && (
          <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>
        )}

        {/* Summary cards */}
        <div className="mb-6 grid grid-cols-3 gap-4">
          {[
            { label: 'مهام مفتوحة', val: totalTasks, color: 'text-blue-700' },
            { label: 'جلسات قادمة', val: totalHearings, color: 'text-amber-600' },
            { label: 'مواعيد معلقة', val: totalDeadlines, color: 'text-red-600' },
          ].map(kpi => (
            <div key={kpi.label} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm text-center">
              <p className={`text-2xl font-bold ${kpi.color}`}>{kpi.val}</p>
              <p className="mt-1 text-xs text-gray-500">{kpi.label}</p>
            </div>
          ))}
        </div>

        {/* Workload table */}
        <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
          <div className="border-b border-gray-100 px-5 py-3">
            <h2 className="text-sm font-semibold text-gray-700">توزيع العبء على المحامين</h2>
          </div>
          {loading ? (
            <p className="px-5 py-8 text-sm text-gray-500">جارٍ التحميل…</p>
          ) : rows.length === 0 ? (
            <p className="px-5 py-8 text-sm text-gray-500">لا توجد بيانات</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-right text-xs text-gray-500">
                  <tr>
                    <th className="px-5 py-3 font-medium">المحامي</th>
                    <th className="px-5 py-3 font-medium text-center">مهام مفتوحة</th>
                    <th className="px-5 py-3 font-medium text-center">جلسات قادمة</th>
                    <th className="px-5 py-3 font-medium text-center">مواعيد معلقة</th>
                    <th className="px-5 py-3 font-medium text-center">مجموع الضغط</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {rows
                    .sort((a, b) =>
                      (b.open_tasks + b.upcoming_hearings + b.pending_deadlines) -
                      (a.open_tasks + a.upcoming_hearings + a.pending_deadlines)
                    )
                    .map(r => {
                      const total = r.open_tasks + r.upcoming_hearings + r.pending_deadlines
                      const maxTotal = Math.max(...rows.map(x => x.open_tasks + x.upcoming_hearings + x.pending_deadlines), 1)
                      return (
                        <tr key={r.user_id} className="hover:bg-gray-50">
                          <td className="px-5 py-3 font-medium">{r.user_name}</td>
                          <td className="px-5 py-3 text-center">
                            <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${r.open_tasks > 5 ? 'bg-red-50 text-red-700' : 'bg-gray-100 text-gray-600'}`}>
                              {r.open_tasks}
                            </span>
                          </td>
                          <td className="px-5 py-3 text-center">
                            <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${r.upcoming_hearings > 3 ? 'bg-amber-50 text-amber-700' : 'bg-gray-100 text-gray-600'}`}>
                              {r.upcoming_hearings}
                            </span>
                          </td>
                          <td className="px-5 py-3 text-center">
                            <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${r.pending_deadlines > 2 ? 'bg-orange-50 text-orange-700' : 'bg-gray-100 text-gray-600'}`}>
                              {r.pending_deadlines}
                            </span>
                          </td>
                          <td className="px-5 py-3">
                            <div className="flex items-center gap-2">
                              <div className="flex-1 h-2 rounded-full bg-gray-100 overflow-hidden">
                                <div
                                  className="h-full rounded-full bg-blue-500"
                                  style={{ width: `${(total / maxTotal) * 100}%` }}
                                />
                              </div>
                              <span className="text-xs font-medium text-gray-700 w-4 text-center">{total}</span>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </AppShell>
    </RequireRole>
  )
}
