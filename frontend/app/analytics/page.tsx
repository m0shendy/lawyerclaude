'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet } from '@/lib/api'
import { RequireRole } from '@/lib/rbac'
import type { RevenuePeriod, AgingBucket, LawyerProductivity } from '@/lib/types'

type GroupBy = 'month' | 'week'

export default function AnalyticsPage() {
  const [groupBy, setGroupBy] = useState<GroupBy>('month')
  const [revenue, setRevenue] = useState<RevenuePeriod[]>([])
  const [aging, setAging] = useState<AgingBucket[]>([])
  const [productivity, setProductivity] = useState<LawyerProductivity[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    Promise.all([
      apiGet<RevenuePeriod[]>(`/analytics/revenue?group_by=${groupBy}`),
      apiGet<AgingBucket[]>('/analytics/aging'),
      apiGet<LawyerProductivity[]>('/analytics/lawyer-productivity'),
    ])
      .then(([r, a, p]) => { setRevenue(r); setAging(a); setProductivity(p) })
      .catch(e => setError(e instanceof ApiError ? e.message : 'حدث خطأ'))
      .finally(() => setLoading(false))
  }, [groupBy])

  const totalRevenue = revenue.reduce((s, r) => s + Number(r.billed_egp), 0)
  const totalCollected = revenue.reduce((s, r) => s + Number(r.collected_egp), 0)
  const totalHours = productivity.reduce((s, p) => s + Number(p.hours_logged), 0)

  const maxRevenue = Math.max(...revenue.map(r => Number(r.billed_egp)), 1)

  return (
    <RequireRole roles={['partner_manager']}>
      <AppShell>
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-xl font-bold">التقارير</h1>
          <div className="flex gap-2">
            <Link
              href="/analytics/operational"
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
            >
              📊 التقرير التشغيلي
            </Link>
            <Link
              href="/analytics/activity"
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
            >
              📋 سجل النشاطات
            </Link>
          </div>
        </div>

        {error && <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>}

        {/* KPI cards */}
        <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[
            { label: 'إجمالي الإيرادات', val: `${totalRevenue.toLocaleString('ar-EG')} ج.م` },
            { label: 'إجمالي المحصَّل', val: `${totalCollected.toLocaleString('ar-EG')} ج.م` },
            { label: 'نسبة التحصيل', val: totalRevenue > 0 ? `${((totalCollected / totalRevenue) * 100).toFixed(1)}%` : '—' },
            { label: 'إجمالي ساعات العمل', val: `${totalHours.toFixed(1)} س` },
          ].map(kpi => (
            <div key={kpi.label} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
              <p className="text-xs text-gray-500">{kpi.label}</p>
              <p className="mt-1 text-lg font-bold">{kpi.val}</p>
            </div>
          ))}
        </div>

        {/* Revenue chart */}
        <div className="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold">الإيرادات</h2>
            <div className="flex gap-1">
              {(['month', 'week'] as GroupBy[]).map(g => (
                <button
                  key={g}
                  onClick={() => setGroupBy(g)}
                  className={`rounded px-3 py-1 text-xs ${groupBy === g ? 'bg-blue-700 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
                >
                  {g === 'month' ? 'شهري' : 'أسبوعي'}
                </button>
              ))}
            </div>
          </div>
          {loading ? (
            <p className="text-sm text-gray-500">جارٍ التحميل…</p>
          ) : revenue.length === 0 ? (
            <p className="text-sm text-gray-500">لا توجد بيانات</p>
          ) : (
            <div className="overflow-x-auto">
              <div className="flex items-end gap-1 h-40 min-w-max">
                {revenue.slice(-12).map(r => {
                  const pct = (Number(r.billed_egp) / maxRevenue) * 100
                  const collectedPct = Number(r.billed_egp) > 0
                    ? (Number(r.collected_egp) / Number(r.billed_egp)) * pct
                    : 0
                  return (
                    <div key={r.period} className="flex flex-col items-center gap-1 w-12">
                      <div className="relative w-8 flex flex-col justify-end" style={{ height: `${pct}%`, minHeight: pct > 0 ? '4px' : '0' }}>
                        <div className="absolute inset-0 rounded-t bg-blue-100" />
                        <div className="absolute inset-x-0 bottom-0 rounded-t bg-blue-600" style={{ height: `${collectedPct}%` }} />
                      </div>
                      <span className="text-xs text-gray-500 truncate w-full text-center">{r.period.slice(-5)}</span>
                    </div>
                  )
                })}
              </div>
              <div className="mt-2 flex gap-4 text-xs text-gray-500">
                <span className="flex items-center gap-1"><span className="inline-block h-2 w-4 rounded bg-blue-100"/> مُفوتَر</span>
                <span className="flex items-center gap-1"><span className="inline-block h-2 w-4 rounded bg-blue-600"/> محصَّل</span>
              </div>
            </div>
          )}
        </div>

        {/* Aging */}
        <div className="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="text-base font-semibold mb-4">تقادم الذمم</h2>
          {loading ? <p className="text-sm text-gray-500">جارٍ التحميل…</p> : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {aging.map(b => {
                const label = b.bucket === 'current' ? 'جارية (0-30 يوم)' :
                  b.bucket === '31-60' ? '31-60 يوم' :
                  b.bucket === '61-90' ? '61-90 يوم' : '+90 يوم'
                const color = b.bucket === 'current' ? 'text-green-700 bg-green-50' :
                  b.bucket === '31-60' ? 'text-yellow-700 bg-yellow-50' :
                  b.bucket === '61-90' ? 'text-orange-700 bg-orange-50' : 'text-red-700 bg-red-50'
                return (
                  <div key={b.bucket} className={`rounded-xl p-4 ${color.split(' ')[1]}`}>
                    <p className={`text-xs font-medium ${color.split(' ')[0]}`}>{label}</p>
                    <p className="mt-1 text-base font-bold">{Number(b.total_egp).toLocaleString('ar-EG')} ج.م</p>
                    <p className={`text-xs ${color.split(' ')[0]} opacity-70`}>{b.count} فاتورة</p>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Lawyer productivity */}
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="text-base font-semibold mb-4">إنتاجية المحامين</h2>
          {loading ? <p className="text-sm text-gray-500">جارٍ التحميل…</p> : productivity.length === 0 ? (
            <p className="text-sm text-gray-500">لا توجد بيانات</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-right">
                  <tr>
                    <th className="px-4 py-2 font-semibold">المحامي</th>
                    <th className="px-4 py-2 font-semibold">الساعات</th>
                    <th className="px-4 py-2 font-semibold">المبلغ القابل للفاتورة</th>
                    <th className="px-4 py-2 font-semibold">ساعات مُفوتَرة</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {productivity.map(p => (
                    <tr key={p.user_id} className="hover:bg-gray-50">
                      <td className="px-4 py-2">{p.name}</td>
                      <td className="px-4 py-2">{Number(p.hours_logged).toFixed(1)} س</td>
                      <td className="px-4 py-2">{Number(p.billed_egp).toLocaleString('ar-EG')} ج.م</td>
                      <td className="px-4 py-2">{'—'}</td>
                      <td className="px-4 py-2">{'—'}</td>
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
