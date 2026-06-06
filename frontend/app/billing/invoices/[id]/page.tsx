'use client'

import { useEffect, useState, type FormEvent } from 'react'
import { useParams } from 'next/navigation'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet, apiPost } from '@/lib/api'
import { RequireRole, useUser } from '@/lib/rbac'
import {
  INVOICE_STATUS_LABELS, INVOICE_STATUS_COLORS, PAYMENT_METHOD_LABELS,
  type InvoiceDetail, type PaymentMethod,
} from '@/lib/types'

export default function InvoiceDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { user } = useUser()
  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showPayment, setShowPayment] = useState(false)
  const [payAmount, setPayAmount] = useState('')
  const [payDate, setPayDate] = useState(new Date().toISOString().slice(0, 10))
  const [payMethod, setPayMethod] = useState<PaymentMethod>('cash')
  const [payRef, setPayRef] = useState('')
  const [payBusy, setPayBusy] = useState(false)

  async function load() {
    setLoading(true)
    try {
      setInvoice(await apiGet<InvoiceDetail>(`/invoices/${id}`))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [id])

  async function onSend() {
    if (!confirm('إرسال الفاتورة للعميل؟')) return
    try {
      await apiPost(`/invoices/${id}/send`)
      load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    }
  }

  async function onCancel() {
    if (!confirm('تأكيد إلغاء الفاتورة؟')) return
    try {
      await apiPost(`/invoices/${id}/cancel`)
      load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    }
  }

  async function onPayment(e: FormEvent) {
    e.preventDefault()
    setPayBusy(true)
    try {
      await apiPost(`/invoices/${id}/payments`, {
        amount_egp: parseFloat(payAmount),
        payment_date: payDate,
        method: payMethod,
        reference: payRef || null,
      })
      setShowPayment(false)
      setPayAmount('')
      setPayRef('')
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'حدث خطأ')
    } finally {
      setPayBusy(false)
    }
  }

  if (loading) return <AppShell><p className="text-sm text-gray-500">جارٍ التحميل…</p></AppShell>
  if (!invoice) return <AppShell><p className="text-sm text-red-600">{error}</p></AppShell>

  const isManager = user?.role === 'partner_manager'
  const isSecretary = user?.role === 'secretary'
  const canEdit = isManager || isSecretary

  return (
    <RequireRole roles={['partner_manager', 'secretary']}>
      <AppShell>
        <div className="mx-auto max-w-3xl">
          <div className="flex items-start justify-between mb-6">
            <div>
              <h1 className="text-xl font-bold">{invoice.invoice_number}</h1>
              <span className={`mt-1 inline-block rounded-full px-3 py-0.5 text-xs ${INVOICE_STATUS_COLORS[invoice.status]}`}>
                {INVOICE_STATUS_LABELS[invoice.status]}
              </span>
            </div>
            <div className="flex gap-2">
              {canEdit && invoice.status === 'draft' && (
                <button onClick={onSend} className="rounded bg-blue-700 px-3 py-1.5 text-sm text-white hover:bg-blue-800">
                  إرسال
                </button>
              )}
              {canEdit && ['sent','partial','overdue'].includes(invoice.status) && (
                <button onClick={() => setShowPayment(v => !v)} className="rounded bg-green-700 px-3 py-1.5 text-sm text-white hover:bg-green-800">
                  تسجيل دفعة
                </button>
              )}
              {isManager && !['paid','cancelled'].includes(invoice.status) && (
                <button onClick={onCancel} className="rounded border border-red-200 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50">
                  إلغاء
                </button>
              )}
            </div>
          </div>

          {error && <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>}

          {/* Payment form */}
          {showPayment && (
            <form onSubmit={onPayment} className="mb-6 rounded-xl border border-green-200 bg-green-50 p-4 space-y-3">
              <h3 className="font-semibold text-green-800">تسجيل دفعة</h3>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium">المبلغ (ج.م) *</label>
                  <input type="number" step="0.01" min="0.01" value={payAmount} onChange={e => setPayAmount(e.target.value)} className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm" required />
                </div>
                <div>
                  <label className="text-xs font-medium">التاريخ *</label>
                  <input type="date" value={payDate} onChange={e => setPayDate(e.target.value)} className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm" required />
                </div>
                <div>
                  <label className="text-xs font-medium">طريقة الدفع</label>
                  <select value={payMethod} onChange={e => setPayMethod(e.target.value as PaymentMethod)} className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm">
                    {(Object.keys(PAYMENT_METHOD_LABELS) as PaymentMethod[]).map(m => (
                      <option key={m} value={m}>{PAYMENT_METHOD_LABELS[m]}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium">رقم المرجع</label>
                  <input value={payRef} onChange={e => setPayRef(e.target.value)} className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm" dir="ltr" />
                </div>
              </div>
              <div className="flex gap-2">
                <button type="submit" disabled={payBusy} className="rounded bg-green-700 px-4 py-1.5 text-sm text-white hover:bg-green-800 disabled:opacity-50">
                  {payBusy ? 'جارٍ الحفظ…' : 'حفظ الدفعة'}
                </button>
                <button type="button" onClick={() => setShowPayment(false)} className="rounded border border-gray-300 px-4 py-1.5 text-sm">
                  إلغاء
                </button>
              </div>
            </form>
          )}

          {/* Summary */}
          <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
            {[
              ['إجمالي', `${Number(invoice.total_egp).toLocaleString('ar-EG')} ج.م`],
              ['مدفوع', `${Number(invoice.amount_paid).toLocaleString('ar-EG')} ج.م`],
              ['متبقي', `${Number(invoice.amount_due).toLocaleString('ar-EG')} ج.م`],
              ['تاريخ الاستحقاق', invoice.due_date],
            ].map(([label, val]) => (
              <div key={label} className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
                <p className="text-xs text-gray-500">{label}</p>
                <p className="mt-1 font-semibold">{val}</p>
              </div>
            ))}
          </div>

          {/* Line items */}
          <h2 className="text-base font-semibold mb-3">بنود الفاتورة</h2>
          <div className="rounded-xl border border-gray-200 bg-white shadow-sm mb-6 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-right">
                <tr>
                  <th className="px-4 py-2 font-semibold">البيان</th>
                  <th className="px-4 py-2 font-semibold">الكمية</th>
                  <th className="px-4 py-2 font-semibold">سعر الوحدة</th>
                  <th className="px-4 py-2 font-semibold">الإجمالي</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {invoice.line_items.map(li => (
                  <tr key={li.id}>
                    <td className="px-4 py-2">{li.description}</td>
                    <td className="px-4 py-2">{li.quantity}</td>
                    <td className="px-4 py-2">{Number(li.unit_price_egp).toLocaleString('ar-EG')} ج.م</td>
                    <td className="px-4 py-2 font-medium">{Number(li.total_egp).toLocaleString('ar-EG')} ج.م</td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="bg-gray-50 text-right text-sm">
                <tr><td colSpan={3} className="px-4 py-2 font-medium">الإجمالي قبل الضريبة</td><td className="px-4 py-2">{Number(invoice.subtotal_egp).toLocaleString('ar-EG')} ج.م</td></tr>
                <tr><td colSpan={3} className="px-4 py-2">ضريبة القيمة المضافة ({invoice.tax_rate}%)</td><td className="px-4 py-2">{Number(invoice.tax_egp).toLocaleString('ar-EG')} ج.م</td></tr>
                {Number(invoice.discount_egp) > 0 && (
                  <tr><td colSpan={3} className="px-4 py-2">خصم</td><td className="px-4 py-2">- {Number(invoice.discount_egp).toLocaleString('ar-EG')} ج.م</td></tr>
                )}
                <tr className="font-bold"><td colSpan={3} className="px-4 py-2">الإجمالي</td><td className="px-4 py-2">{Number(invoice.total_egp).toLocaleString('ar-EG')} ج.م</td></tr>
              </tfoot>
            </table>
          </div>

          {/* Payment history */}
          {invoice.payments.length > 0 && (
            <>
              <h2 className="text-base font-semibold mb-3">سجل المدفوعات</h2>
              <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-right">
                    <tr>
                      <th className="px-4 py-2 font-semibold">التاريخ</th>
                      <th className="px-4 py-2 font-semibold">المبلغ</th>
                      <th className="px-4 py-2 font-semibold">الطريقة</th>
                      <th className="px-4 py-2 font-semibold">المرجع</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {invoice.payments.map(p => (
                      <tr key={p.id}>
                        <td className="px-4 py-2">{p.payment_date}</td>
                        <td className="px-4 py-2 font-medium">{Number(p.amount_egp).toLocaleString('ar-EG')} ج.م</td>
                        <td className="px-4 py-2">{p.method ? PAYMENT_METHOD_LABELS[p.method] : '—'}</td>
                        <td className="px-4 py-2 dir-ltr text-xs text-gray-500">{p.reference ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </AppShell>
    </RequireRole>
  )
}
