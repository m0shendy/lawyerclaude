'use client'

// Billing dashboard — outstanding invoices, aging summary, quick links.

import { useEffect, useState } from 'react'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet } from '@/lib/api'
import { RequireRole } from '@/lib/rbac'
import {
  INVOICE_STATUS_LABELS, INVOICE_STATUS_COLORS,
  type Invoice, type AgingBucket,
} from '@/lib/types'

export default function BillingPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [aging, setAging] = useState<AgingBucket[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        const [invData, agingData] = await Promise.all([
          apiGet<Invoice[]>('/invoices?status=sent'),
          apiGet<AgingBucket[]>('/analytics/aging'),
        ])
        setInvoices(invData)
        setAging(agingData)
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'حدث خطأ')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const overdue = invoices.filter(i => {
    const due = new Date(i.due_date)
    return due < new Date() && i.status !== 'paid' && i.status !== 'cancelled'
  })

  return (
    <RequireRole roles={['partner_manager', 'secretary']}>
      <AppShell>
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-bold">الفواتير والأتعاب</h1>
          <div className="flex gap-2">
            <Link href="/billing/invoices/new" className="rounded bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800">
              + فاتورة جديدة
            </Link>
            <Link href="/billing/time" className="rounded border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">
              قيود الوقت
            </Link>
          </div>
        </div>

        {error && <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>}

        {!loading && (
          <>
            {/* Aging buckets */}
            <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
              {aging.map(b => (
                <div key={b.bucket} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm text-center">
                  <p className="text-xs text-gray-500 mb-1">
                    {b.bucket === 'current' ? 'جارية' : `${b.bucket} يوم`}
                  </p>
                  <p className="text-lg font-bold text-gray-800">{Number(b.total_egp).toLocaleString('ar-EG')} ج.م</p>
                  <p className="text-xs text-gray-400">{b.count} فاتورة</p>
                </div>
              ))}
            </div>

            {/* Overdue callout */}
            {overdue.length > 0 && (
              <div className="mb-4 rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                ⚠️ {overdue.length} فاتورة متأخرة تحتاج إلى متابعة
              </div>
            )}

            {/* Quick links */}
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 mb-6">
              {[
                { href: '/billing/invoices', label: 'كل الفواتير' },
                { href: '/billing/invoices?status=draft', label: 'المسودات' },
                { href: '/billing/time', label: 'قيود الوقت' },
                { href: '/billing/rates', label: 'أسعار المحامين' },
              ].map(l => (
                <Link key={l.href} href={l.href}
                  className="rounded-xl border border-gray-200 bg-white p-4 text-center text-sm font-medium hover:bg-gray-50 shadow-sm">
                  {l.label}
                </Link>
              ))}
            </div>

            {/* Recent sent invoices */}
            <h2 className="text-base font-semibold mb-3">الفواتير المُرسَلة ({invoices.length})</h2>
            {invoices.length === 0 ? (
              <p className="text-sm text-gray-500">لا توجد فواتير مُرسَلة</p>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-right">
                    <tr>
                      <th className="px-4 py-3 font-semibold">رقم الفاتورة</th>
                      <th className="px-4 py-3 font-semibold">الإجمالي</th>
                      <th className="px-4 py-3 font-semibold">تاريخ الاستحقاق</th>
                      <th className="px-4 py-3 font-semibold">الحالة</th>
                      <th className="px-4 py-3"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {invoices.slice(0, 20).map(inv => (
                      <tr key={inv.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-mono text-xs">{inv.invoice_number}</td>
                        <td className="px-4 py-3 font-medium">{Number(inv.total_egp).toLocaleString('ar-EG')} ج.م</td>
                        <td className="px-4 py-3 text-gray-600">{inv.due_date}</td>
                        <td className="px-4 py-3">
                          <span className={`rounded-full px-2 py-0.5 text-xs ${INVOICE_STATUS_COLORS[inv.status]}`}>
                            {INVOICE_STATUS_LABELS[inv.status]}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <Link href={`/billing/invoices/${inv.id}`} className="text-blue-700 hover:underline">عرض</Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </AppShell>
    </RequireRole>
  )
}
