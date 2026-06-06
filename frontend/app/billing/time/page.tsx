'use client'

import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet, apiPost, apiDelete } from '@/lib/api'
import { ALL_ROLES, RequireRole, useUser } from '@/lib/rbac'
import type { TimeEntry } from '@/lib/types'

export default function TimeEntriesPage() {
  const { user } = useUser()
  const [entries, setEntries] = useState<TimeEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [caseId, setCaseId] = useState('')
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [minutes, setMinutes] = useState('')
  const [desc, setDesc] = useState('')
  const [billable, setBillable] = useState(true)
  const [busy, setBusy] = useState(false)

  async function load() {
    setLoading(true)
    try {
      setEntries(await apiGet<TimeEntry[]>('/time-entries'))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await apiPost('/time-entries', {
        case_id: caseId,
        date,
        duration_minutes: parseInt(minutes),
        description: desc,
        is_billable: billable,
      })
      setCaseId(''); setMinutes(''); setDesc(''); setShowForm(false)
      load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    } finally {
      setBusy(false)
    }
  }

  async function onDelete(id: string) {
    if (!confirm('حذف هذا القيد؟')) return
    try {
      await apiDelete(`/time-entries/${id}`)
      load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    }
  }

  const inp = 'w-full rounded border border-gray-300 px-3 py-2 text-sm'

  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold">قيود الوقت</h1>
          <button onClick={() => setShowForm(v => !v)} className="rounded bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800">
            + قيد جديد
          </button>
        </div>

        {error && <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>}

        {showForm && (
          <form onSubmit={onSubmit} className="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-3">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="sm:col-span-2">
                <label className="mb-1 block text-xs font-medium">معرّف القضية *</label>
                <input value={caseId} onChange={e => setCaseId(e.target.value)} className={inp} required placeholder="UUID القضية" dir="ltr" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">التاريخ *</label>
                <input type="date" value={date} onChange={e => setDate(e.target.value)} className={inp} required />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">المدة (دقيقة) *</label>
                <input type="number" min="1" value={minutes} onChange={e => setMinutes(e.target.value)} className={inp} required />
              </div>
              <div className="sm:col-span-3">
                <label className="mb-1 block text-xs font-medium">الوصف *</label>
                <input value={desc} onChange={e => setDesc(e.target.value)} className={inp} required />
              </div>
              <div className="flex items-center gap-2 pt-5">
                <input type="checkbox" id="billable" checked={billable} onChange={e => setBillable(e.target.checked)} className="h-4 w-4" />
                <label htmlFor="billable" className="text-sm">قابل للفاتورة</label>
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

        {loading ? <p className="text-sm text-gray-500">جارٍ التحميل…</p> : entries.length === 0 ? (
          <p className="text-sm text-gray-500">لا توجد قيود</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-right">
                <tr>
                  <th className="px-4 py-3 font-semibold">التاريخ</th>
                  <th className="px-4 py-3 font-semibold">الوصف</th>
                  <th className="px-4 py-3 font-semibold">المدة</th>
                  <th className="px-4 py-3 font-semibold">المبلغ</th>
                  <th className="px-4 py-3 font-semibold">قابل للفاتورة</th>
                  <th className="px-4 py-3 font-semibold">فاتورة</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {entries.map(e => (
                  <tr key={e.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">{e.date}</td>
                    <td className="px-4 py-3">{e.description}</td>
                    <td className="px-4 py-3">{Math.floor(e.duration_minutes / 60)}س {e.duration_minutes % 60}د</td>
                    <td className="px-4 py-3">{e.amount_egp ? `${Number(e.amount_egp).toLocaleString('ar-EG')} ج.م` : '—'}</td>
                    <td className="px-4 py-3">{e.is_billable ? '✓' : '—'}</td>
                    <td className="px-4 py-3 text-xs text-gray-400">{e.invoice_id ? 'مُفوتَر' : '—'}</td>
                    <td className="px-4 py-3">
                      {!e.invoice_id && (
                        <button onClick={() => onDelete(e.id)} className="text-red-600 hover:underline text-xs">حذف</button>
                      )}
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
