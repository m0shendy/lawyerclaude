'use client'

import { useState, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import AppShell from '@/components/AppShell'
import { ApiError, apiPost } from '@/lib/api'
import { RequireRole } from '@/lib/rbac'
import type { InvoiceDetail } from '@/lib/types'

interface LineItemForm { description: string; quantity: string; unit_price_egp: string }

export default function NewInvoicePage() {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dueDate, setDueDate] = useState('')
  const [taxRate, setTaxRate] = useState('14')
  const [discount, setDiscount] = useState('0')
  const [notes, setNotes] = useState('')
  const [lines, setLines] = useState<LineItemForm[]>([
    { description: '', quantity: '1', unit_price_egp: '' },
  ])

  function addLine() {
    setLines(l => [...l, { description: '', quantity: '1', unit_price_egp: '' }])
  }

  function removeLine(i: number) {
    setLines(l => l.filter((_, idx) => idx !== i))
  }

  function updateLine(i: number, field: keyof LineItemForm, val: string) {
    setLines(l => l.map((li, idx) => idx === i ? { ...li, [field]: val } : li))
  }

  const subtotal = lines.reduce((sum, li) => {
    const q = parseFloat(li.quantity) || 0
    const p = parseFloat(li.unit_price_egp) || 0
    return sum + q * p
  }, 0)
  const tax = subtotal * (parseFloat(taxRate) || 14) / 100
  const total = subtotal + tax - (parseFloat(discount) || 0)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!dueDate) { setError('تاريخ الاستحقاق مطلوب'); return }
    setBusy(true)
    setError(null)
    try {
      const created = await apiPost<InvoiceDetail>('/invoices', {
        due_date: dueDate,
        tax_rate: parseFloat(taxRate),
        discount_egp: parseFloat(discount) || 0,
        notes: notes || null,
        line_items: lines.filter(l => l.description).map(l => ({
          description: l.description,
          quantity: parseFloat(l.quantity) || 1,
          unit_price_egp: parseFloat(l.unit_price_egp) || 0,
          total_egp: (parseFloat(l.quantity) || 1) * (parseFloat(l.unit_price_egp) || 0),
        })),
      })
      router.push(`/billing/invoices/${created.id}`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ غير متوقع')
    } finally {
      setBusy(false)
    }
  }

  const inp = 'w-full rounded border border-gray-300 px-3 py-2 text-sm'

  return (
    <RequireRole roles={['partner_manager', 'secretary']}>
      <AppShell>
        <div className="mx-auto max-w-3xl">
          <h1 className="mb-6 text-xl font-bold">فاتورة جديدة</h1>
          {error && <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>}

          <form onSubmit={onSubmit} className="space-y-6">
            {/* Header */}
            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="mb-3 font-semibold text-sm">بيانات الفاتورة</h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div>
                  <label className="mb-1 block text-sm font-medium">تاريخ الاستحقاق *</label>
                  <input type="date" value={dueDate} onChange={e => setDueDate(e.target.value)} className={inp} required />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">نسبة الضريبة %</label>
                  <input type="number" step="0.01" min="0" value={taxRate} onChange={e => setTaxRate(e.target.value)} className={inp} />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">خصم (ج.م)</label>
                  <input type="number" step="0.01" min="0" value={discount} onChange={e => setDiscount(e.target.value)} className={inp} />
                </div>
                <div className="sm:col-span-3">
                  <label className="mb-1 block text-sm font-medium">ملاحظات</label>
                  <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2} className={inp} />
                </div>
              </div>
            </div>

            {/* Line items */}
            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-semibold text-sm">بنود الفاتورة</h2>
                <button type="button" onClick={addLine} className="text-xs text-blue-700 hover:underline">+ إضافة بند</button>
              </div>
              <div className="space-y-3">
                {lines.map((li, i) => (
                  <div key={i} className="grid grid-cols-12 gap-2 items-end">
                    <div className="col-span-6">
                      {i === 0 && <label className="mb-1 block text-xs font-medium">البيان</label>}
                      <input value={li.description} onChange={e => updateLine(i, 'description', e.target.value)} placeholder="وصف الخدمة" className={inp} />
                    </div>
                    <div className="col-span-2">
                      {i === 0 && <label className="mb-1 block text-xs font-medium">الكمية</label>}
                      <input type="number" step="0.01" min="0" value={li.quantity} onChange={e => updateLine(i, 'quantity', e.target.value)} className={inp} />
                    </div>
                    <div className="col-span-3">
                      {i === 0 && <label className="mb-1 block text-xs font-medium">السعر (ج.م)</label>}
                      <input type="number" step="0.01" min="0" value={li.unit_price_egp} onChange={e => updateLine(i, 'unit_price_egp', e.target.value)} className={inp} />
                    </div>
                    <div className="col-span-1 flex justify-end">
                      {lines.length > 1 && (
                        <button type="button" onClick={() => removeLine(i)} className="text-red-500 hover:text-red-700 text-lg leading-none">×</button>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Totals */}
              <div className="mt-4 border-t border-gray-100 pt-3 text-sm space-y-1 text-left">
                <div className="flex justify-between"><span className="text-gray-500">الإجمالي قبل الضريبة</span><span>{subtotal.toLocaleString('ar-EG', { minimumFractionDigits: 2 })} ج.م</span></div>
                <div className="flex justify-between"><span className="text-gray-500">ضريبة ({taxRate}%)</span><span>{tax.toLocaleString('ar-EG', { minimumFractionDigits: 2 })} ج.م</span></div>
                {parseFloat(discount) > 0 && <div className="flex justify-between"><span className="text-gray-500">خصم</span><span>- {parseFloat(discount).toLocaleString('ar-EG', { minimumFractionDigits: 2 })} ج.م</span></div>}
                <div className="flex justify-between font-bold pt-1 border-t border-gray-200"><span>الإجمالي</span><span>{total.toLocaleString('ar-EG', { minimumFractionDigits: 2 })} ج.م</span></div>
              </div>
            </div>

            <div className="flex gap-3">
              <button type="submit" disabled={busy} className="rounded bg-blue-700 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50">
                {busy ? 'جارٍ الحفظ…' : 'إنشاء الفاتورة'}
              </button>
              <button type="button" onClick={() => router.back()} className="rounded border border-gray-300 px-5 py-2 text-sm hover:bg-gray-50">إلغاء</button>
            </div>
          </form>
        </div>
      </AppShell>
    </RequireRole>
  )
}
