'use client'

import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet, apiPost, apiPatch, apiDelete } from '@/lib/api'
import { RequireRole } from '@/lib/rbac'
import type { BillingRate } from '@/lib/types'

export default function BillingRatesPage() {
  const [rates, setRates] = useState<BillingRate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [userId, setUserId] = useState('')
  const [rateEgp, setRateEgp] = useState('')
  const [effectiveFrom, setEffectiveFrom] = useState(new Date().toISOString().slice(0, 10))
  const [busy, setBusy] = useState(false)

  async function load() {
    setLoading(true)
    try {
      setRates(await apiGet<BillingRate[]>('/billing-rates'))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  function openEdit(r: BillingRate) {
    setEditId(r.id)
    setUserId(r.user_id)
    setRateEgp(String(r.rate_egp))
    setEffectiveFrom(r.effective_from)
    setShowForm(true)
  }

  function openNew() {
    setEditId(null); setUserId(''); setRateEgp(''); setEffectiveFrom(new Date().toISOString().slice(0, 10))
    setShowForm(true)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (editId) {
        await apiPatch(`/billing-rates/${editId}`, { rate_egp: parseFloat(rateEgp), effective_from: effectiveFrom })
      } else {
        await apiPost('/billing-rates', { user_id: userId, rate_egp: parseFloat(rateEgp), effective_from: effectiveFrom })
      }
      setShowForm(false)
      load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    } finally {
      setBusy(false)
    }
  }

  async function onDelete(id: string) {
    if (!confirm('حذف هذا السعر؟')) return
    try {
      await apiDelete(`/billing-rates/${id}`)
      load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    }
  }

  const inp = 'w-full rounded border border-gray-300 px-3 py-2 text-sm'

  return (
    <RequireRole roles={['partner_manager']}>
      <AppShell>
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold">أسعار المحامين بالساعة</h1>
          <button onClick={openNew} className="rounded bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800">
            + سعر جديد
          </button>
        </div>

        {error && <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>}

        {showForm && (
          <form onSubmit={onSubmit} className="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-3">
            <h2 className="font-semibold text-sm">{editId ? 'تعديل السعر' : 'سعر جديد'}</h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {!editId && (
                <div>
                  <label className="mb-1 block text-xs font-medium">معرّف المحامي (UUID) *</label>
                  <input value={userId} onChange={e => setUserId(e.target.value)} className={inp} required dir="ltr" placeholder="user UUID" />
                </div>
              )}
              <div>
                <label className="mb-1 block text-xs font-medium">السعر بالساعة (ج.م) *</label>
                <input type="number" step="0.01" min="0" value={rateEgp} onChange={e => setRateEgp(e.target.value)} className={inp} required />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">ساري من *</label>
                <input type="date" value={effectiveFrom} onChange={e => setEffectiveFrom(e.target.value)} className={inp} required />
              </div>
            </div>
            <div className="flex gap-2">
              <button type="submit" disabled={busy} className="rounded bg-blue-700 px-4 py-2 text-sm text-white hover:bg-blue-800 disabled:opacity-50">
                {busy ? 'جارٍ الحفظ…' : 'حفظ'}
              </button>
              <button type="button" onClick={() => setShowForm(false)} className="rounded border border-gray-300 px-4 py-2 text-sm">إلغاء</button>
            </div>
          </form>
        )}

        {loading ? <p className="text-sm text-gray-500">جارٍ التحميل…</p> : rates.length === 0 ? (
          <p className="text-sm text-gray-500">لا توجد أسعار مسجّلة</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-right">
                <tr>
                  <th className="px-4 py-3 font-semibold">المحامي (UUID)</th>
                  <th className="px-4 py-3 font-semibold">السعر / ساعة</th>
                  <th className="px-4 py-3 font-semibold">ساري من</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {rates.map(r => (
                  <tr key={r.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-xs font-mono">{r.user_id}</td>
                    <td className="px-4 py-3 font-medium">{Number(r.rate_egp).toLocaleString('ar-EG')} ج.م</td>
                    <td className="px-4 py-3 text-gray-600">{r.effective_from}</td>
                    <td className="px-4 py-3 flex gap-3">
                      <button onClick={() => openEdit(r)} className="text-blue-700 hover:underline text-xs">تعديل</button>
                      <button onClick={() => onDelete(r.id)} className="text-red-600 hover:underline text-xs">حذف</button>
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
