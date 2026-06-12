'use client'

// Financial analytics report (spec 002 US10, T084).
// Date range picker → GET /analytics/financial → revenue, outstanding, payment method breakdown.
// Partner manager only [C-IV].

import { useEffect, useState, type FormEvent } from 'react'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet } from '@/lib/api'
import { RequireRole } from '@/lib/rbac'

interface FinancialReport {
  period_from: string
  period_to: string
  total_invoiced: number
  total_collected: number
  total_outstanding: number
  invoices_count: number
  paid_count: number
  partial_count: number
  pending_count: number
  cancelled_count: number
  payment_methods: Array<{ method: string; amount: number; count: number }>
  monthly_revenue: Array<{ month: string; invoiced: number; collected: number }>
}

const METHOD_AR: Record<string, string> = {
  cash: 'نقداً',
  bank_transfer: 'تحويل بنكي',
  cheque: 'شيك',
  electronic_wallet: 'محفظة إلكترونية',
  card: 'بطاقة',
}

function fmtMoney(n: number) {
  return new Intl.NumberFormat('ar-EG', { minimumFractionDigits: 2 }).format(n) + ' ج.م'
}

function pct(part: number, total: number) {
  if (!total) return 0
  return Math.round((part / total) * 100)
}

function FinancialScreen() {
  const today = new Date().toISOString().slice(0, 10)
  const monthStart = today.slice(0, 8) + '01'

  const [from, setFrom] = useState(monthStart)
  const [to, setTo] = useState(today)
  const [report, setReport] = useState<FinancialReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function load(e?: FormEvent) {
    e?.preventDefault()
    setLoading(true); setErr(null)
    try {
      const data = await apiGet<FinancialReport>(`/analytics/financial?from=${from}&to=${to}`)
      setReport(data)
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : 'تعذّر تحميل التقرير')
    } finally { setLoading(false) }
  }

  useEffect(() => { void load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <div className="mb-4 flex items-center gap-3">
        <Link href="/analytics" className="text-sm text-gray-500 hover:text-gray-700">← التحليلات</Link>
        <span className="text-gray-300">/</span>
        <h1 className="text-xl font-bold">التقرير المالي</h1>
      </div>

      {/* Date range */}
      <form onSubmit={load} className="mb-6 flex flex-wrap items-end gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <label className="text-sm">
          من
          <input type="date" value={from} onChange={e => setFrom(e.target.value)}
            className="mt-1 block rounded border border-gray-300 px-2 py-1.5 text-sm" />
        </label>
        <label className="text-sm">
          إلى
          <input type="date" value={to} onChange={e => setTo(e.target.value)}
            className="mt-1 block rounded border border-gray-300 px-2 py-1.5 text-sm" />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="rounded-lg bg-blue-700 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
        >
          {loading ? 'جارٍ التحميل…' : 'عرض التقرير'}
        </button>
      </form>

      {err && (
        <div className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{err}</div>
      )}

      {report && (
        <div className="space-y-5">
          {/* KPI bar */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: 'إجمالي الفواتير', value: fmtMoney(report.total_invoiced), color: 'blue' },
              { label: 'إجمالي المحصّل', value: fmtMoney(report.total_collected), color: 'green' },
              { label: 'إجمالي المتبقي', value: fmtMoney(report.total_outstanding), color: 'red' },
              { label: 'معدل التحصيل', value: `${pct(report.total_collected, report.total_invoiced)}%`, color: 'purple' },
            ].map(card => (
              <div key={card.label} className={`rounded-xl border p-4 shadow-sm bg-${card.color}-50 border-${card.color}-200`}>
                <p className={`text-xs text-${card.color}-600`}>{card.label}</p>
                <p className={`mt-1 text-lg font-bold text-${card.color}-800`} dir="ltr">{card.value}</p>
              </div>
            ))}
          </div>

          {/* Invoice status counts */}
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="mb-3 text-sm font-bold text-gray-700">توزيع حالات الفواتير</h2>
            <div className="flex flex-wrap gap-3 text-sm">
              {[
                { label: 'مدفوعة', count: report.paid_count, color: 'green' },
                { label: 'جزئية', count: report.partial_count, color: 'amber' },
                { label: 'معلّقة', count: report.pending_count, color: 'blue' },
                { label: 'ملغاة', count: report.cancelled_count, color: 'gray' },
              ].map(s => (
                <span key={s.label} className={`rounded-full bg-${s.color}-100 px-3 py-1 text-${s.color}-800 font-medium`}>
                  {s.label}: {s.count}
                </span>
              ))}
            </div>
          </div>

          {/* Payment methods breakdown */}
          {report.payment_methods.length > 0 && (
            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="mb-3 text-sm font-bold text-gray-700">طرق الدفع</h2>
              <div className="space-y-2">
                {report.payment_methods.map(m => {
                  const barPct = pct(m.amount, report.total_collected)
                  return (
                    <div key={m.method} className="flex items-center gap-3 text-sm">
                      <span className="w-28 shrink-0 text-gray-600">{METHOD_AR[m.method] ?? m.method}</span>
                      <div className="flex-1 h-2 rounded-full bg-gray-100 overflow-hidden">
                        <div className="h-full rounded-full bg-blue-500" style={{ width: `${barPct}%` }} />
                      </div>
                      <span className="shrink-0 text-gray-500 text-xs w-24 text-left" dir="ltr">
                        {fmtMoney(m.amount)} ({m.count})
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Monthly revenue table */}
          {report.monthly_revenue.length > 0 && (
            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="mb-3 text-sm font-bold text-gray-700">الإيرادات الشهرية</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-right text-xs text-gray-500">
                      <th className="pb-2 pr-2">الشهر</th>
                      <th className="pb-2">إجمالي الفواتير</th>
                      <th className="pb-2">المحصّل</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.monthly_revenue.map(row => (
                      <tr key={row.month} className="border-b last:border-0">
                        <td className="py-1.5 pr-2 text-gray-600">{row.month}</td>
                        <td className="py-1.5 text-gray-800" dir="ltr">{fmtMoney(row.invoiced)}</td>
                        <td className="py-1.5 text-green-700 font-medium" dir="ltr">{fmtMoney(row.collected)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  )
}

export default function FinancialPage() {
  return (
    <RequireRole roles={['partner_manager']}>
      <AppShell>
        <FinancialScreen />
      </AppShell>
    </RequireRole>
  )
}
