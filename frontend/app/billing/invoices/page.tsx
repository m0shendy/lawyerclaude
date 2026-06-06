'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet } from '@/lib/api'
import { RequireRole } from '@/lib/rbac'
import { INVOICE_STATUS_LABELS, INVOICE_STATUS_COLORS, type Invoice, type InvoiceStatus } from '@/lib/types'

const STATUS_OPTS: InvoiceStatus[] = ['draft', 'sent', 'partial', 'paid', 'cancelled', 'overdue']

export default function InvoicesListPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<InvoiceStatus | ''>('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const q = statusFilter ? `?status=${statusFilter}` : ''
        setInvoices(await apiGet<Invoice[]>(`/invoices${q}`))
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'حدث خطأ')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [statusFilter])

  return (
    <RequireRole roles={['partner_manager', 'secretary']}>
      <AppShell>
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold">الفواتير</h1>
          <Link href="/billing/invoices/new" className="rounded bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800">
            + فاتورة جديدة
          </Link>
        </div>

        <div className="mb-4 flex gap-2 flex-wrap">
          <button
            onClick={() => setStatusFilter('')}
            className={`rounded-full px-3 py-1 text-xs ${statusFilter === '' ? 'bg-blue-700 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
          >
            الكل
          </button>
          {STATUS_OPTS.map(s => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`rounded-full px-3 py-1 text-xs ${statusFilter === s ? 'bg-blue-700 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
            >
              {INVOICE_STATUS_LABELS[s]}
            </button>
          ))}
        </div>

        {error && <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>}

        {loading ? <p className="text-sm text-gray-500">جارٍ التحميل…</p> : invoices.length === 0 ? (
          <p className="text-sm text-gray-500">لا توجد فواتير</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-right">
                <tr>
                  <th className="px-4 py-3 font-semibold">رقم الفاتورة</th>
                  <th className="px-4 py-3 font-semibold">الإصدار</th>
                  <th className="px-4 py-3 font-semibold">الاستحقاق</th>
                  <th className="px-4 py-3 font-semibold">الإجمالي</th>
                  <th className="px-4 py-3 font-semibold">الحالة</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {invoices.map(inv => (
                  <tr key={inv.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-xs">{inv.invoice_number}</td>
                    <td className="px-4 py-3 text-gray-600">{inv.issue_date}</td>
                    <td className="px-4 py-3 text-gray-600">{inv.due_date}</td>
                    <td className="px-4 py-3 font-medium">{Number(inv.total_egp).toLocaleString('ar-EG')} ج.م</td>
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
      </AppShell>
    </RequireRole>
  )
}
