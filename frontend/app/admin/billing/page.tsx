'use client'

// US4 billing oversight (T026): subscriptions table, events inbox, resolve dialog,
// manual payment form. No work-product fields anywhere. [FR-310]

import { useEffect, useState } from 'react'
import { adminGet, adminPost } from '@/lib/adminApi'

interface SubscriptionItem {
  id: string
  firm_id: string
  firm_name: string
  plan: string | null
  status: string
  provider: string | null
  current_period_end: string | null
  created_at: string
}

interface BillingEventItem {
  id: string
  event_type: string
  provider: string | null
  provider_ref: string | null
  amount_cents: number | null
  payload: Record<string, unknown> | null
  processed_at: string | null
  created_at: string
  resolved: boolean
  resolution_note: string | null
}

const SUB_STATUS_COLOR: Record<string, string> = {
  active: 'bg-green-100 text-green-700',
  trial: 'bg-blue-100 text-blue-700',
  past_due: 'bg-amber-100 text-amber-700',
  cancelled: 'bg-gray-100 text-gray-500',
}

function PayloadModal({ payload, onClose }: { payload: unknown; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" dir="ltr">
      <div className="w-full max-w-xl rounded-xl bg-white p-5 shadow-xl">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold">Payload</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700">✕</button>
        </div>
        <pre className="max-h-96 overflow-auto rounded bg-gray-50 p-3 text-xs">
          {JSON.stringify(payload, null, 2)}
        </pre>
      </div>
    </div>
  )
}

function ResolveDialog({
  event,
  onConfirm,
  onCancel,
  busy,
}: {
  event: BillingEventItem
  onConfirm: (note: string) => void
  onCancel: () => void
  busy: boolean
}) {
  const [note, setNote] = useState('')
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" dir="rtl">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-2 text-lg font-bold">معالجة حدث الفوترة</h2>
        <p className="mb-3 text-sm text-gray-500">المرجع: {event.provider_ref ?? event.id}</p>
        <textarea
          rows={3}
          placeholder="ملاحظة المعالجة (مطلوبة)…"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          className="mb-4 w-full rounded border border-gray-300 px-3 py-2 text-sm"
        />
        <div className="flex gap-2">
          <button
            disabled={!note.trim() || busy}
            onClick={() => onConfirm(note)}
            className="flex-1 rounded bg-blue-600 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {busy ? 'جارٍ التنفيذ…' : 'تأكيد'}
          </button>
          <button
            onClick={onCancel}
            className="flex-1 rounded border border-gray-300 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            إلغاء
          </button>
        </div>
      </div>
    </div>
  )
}

function ManualPaymentForm({
  firmId,
  firmName,
  onSuccess,
  onCancel,
}: {
  firmId: string
  firmName: string
  onSuccess: () => void
  onCancel: () => void
}) {
  const [amount, setAmount] = useState('')
  const [paidDate, setPaidDate] = useState(new Date().toISOString().split('T')[0])
  const [reference, setReference] = useState('')
  const [note, setNote] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      await adminPost(`/admin/firms/${firmId}/manual-payment`, {
        amount_egp: parseFloat(amount),
        paid_date: paidDate,
        reference,
        note,
        confirm: true,
      })
      onSuccess()
    } catch (e: unknown) {
      setError((e as { message?: string }).message ?? 'حدث خطأ')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" dir="rtl">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-2 text-lg font-bold">تسجيل دفعة يدوية</h2>
        <p className="mb-3 text-sm text-gray-500">المكتب: <span className="font-semibold">{firmName}</span></p>
        {error && <p className="mb-3 text-sm text-red-600">{error}</p>}
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium">المبلغ (جنيه)</label>
            <input type="number" min="0" step="0.01" value={amount} onChange={e => setAmount(e.target.value)}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">تاريخ الدفع</label>
            <input type="date" value={paidDate} onChange={e => setPaidDate(e.target.value)}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">المرجع</label>
            <input type="text" value={reference} onChange={e => setReference(e.target.value)}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">ملاحظة</label>
            <textarea rows={2} value={note} onChange={e => setNote(e.target.value)}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm" />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={confirm} onChange={e => setConfirm(e.target.checked)} />
            أؤكد تسجيل هذه الدفعة وتفعيل الاشتراك
          </label>
        </div>
        <div className="mt-4 flex gap-2">
          <button
            disabled={!amount || !reference.trim() || !note.trim() || !confirm || busy}
            onClick={submit}
            className="flex-1 rounded bg-green-600 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-50"
          >
            {busy ? 'جارٍ التنفيذ…' : 'تسجيل الدفعة'}
          </button>
          <button onClick={onCancel}
            className="flex-1 rounded border border-gray-300 py-2 text-sm text-gray-700 hover:bg-gray-50">
            إلغاء
          </button>
        </div>
      </div>
    </div>
  )
}

export default function AdminBillingPage() {
  const [tab, setTab] = useState<'subscriptions' | 'events'>('subscriptions')
  const [subs, setSubs] = useState<SubscriptionItem[]>([])
  const [events, setEvents] = useState<BillingEventItem[]>([])
  const [unprocessedOnly, setUnprocessedOnly] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [payloadEvent, setPayloadEvent] = useState<BillingEventItem | null>(null)
  const [resolveEvent, setResolveEvent] = useState<BillingEventItem | null>(null)
  const [resolveBusy, setResolveBusy] = useState(false)
  const [manualPayment, setManualPayment] = useState<SubscriptionItem | null>(null)

  function showToast(msg: string) {
    setToast(msg)
    setTimeout(() => setToast(null), 4000)
  }

  async function loadSubs() {
    setLoading(true)
    try {
      const data = await adminGet<SubscriptionItem[]>('/admin/subscriptions')
      setSubs(data)
    } catch {
      setError('فشل تحميل الاشتراكات')
    } finally {
      setLoading(false)
    }
  }

  async function loadEvents() {
    setLoading(true)
    try {
      const url = unprocessedOnly ? '/admin/billing-events?unprocessed=true' : '/admin/billing-events'
      const data = await adminGet<BillingEventItem[]>(url)
      setEvents(data)
    } catch {
      setError('فشل تحميل أحداث الفوترة')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (tab === 'subscriptions') loadSubs()
    else loadEvents()
  }, [tab, unprocessedOnly])

  async function handleResolve(note: string) {
    if (!resolveEvent) return
    setResolveBusy(true)
    try {
      await adminPost(`/admin/billing-events/${resolveEvent.id}/resolve`, { note })
      setResolveEvent(null)
      showToast('تم تسجيل المعالجة في سجل التدقيق')
      loadEvents()
    } catch (e: unknown) {
      setError((e as { message?: string }).message ?? 'حدث خطأ')
      setResolveEvent(null)
    } finally {
      setResolveBusy(false)
    }
  }

  return (
    <div dir="rtl">
      {toast && (
        <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white shadow-lg">
          {toast}
        </div>
      )}
      {payloadEvent && <PayloadModal payload={payloadEvent.payload} onClose={() => setPayloadEvent(null)} />}
      {resolveEvent && (
        <ResolveDialog
          event={resolveEvent}
          onConfirm={handleResolve}
          onCancel={() => setResolveEvent(null)}
          busy={resolveBusy}
        />
      )}
      {manualPayment && (
        <ManualPaymentForm
          firmId={manualPayment.firm_id}
          firmName={manualPayment.firm_name}
          onSuccess={() => { setManualPayment(null); showToast('تم تفعيل الاشتراك وتسجيل الدفعة'); loadSubs() }}
          onCancel={() => setManualPayment(null)}
        />
      )}

      <h1 className="mb-4 text-xl font-bold">الفوترة والاشتراكات</h1>

      {/* Tabs */}
      <div className="mb-4 flex gap-2">
        {(['subscriptions', 'events'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-full px-4 py-1 text-sm font-medium ${
              tab === t ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {t === 'subscriptions' ? 'الاشتراكات' : 'أحداث الفوترة'}
          </button>
        ))}
      </div>

      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}

      {/* Subscriptions tab */}
      {tab === 'subscriptions' && (
        <div className="overflow-x-auto rounded border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-gray-200 bg-gray-50 text-right">
              <tr>
                <th className="px-4 py-2 font-medium">المكتب</th>
                <th className="px-4 py-2 font-medium">الخطة</th>
                <th className="px-4 py-2 font-medium">الحالة</th>
                <th className="px-4 py-2 font-medium">مزود الدفع</th>
                <th className="px-4 py-2 font-medium">نهاية الفترة</th>
                <th className="px-4 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={6} className="px-4 py-6 text-center text-gray-400">جارٍ التحميل…</td></tr>
              )}
              {!loading && subs.map((s) => (
                <tr key={s.id} className="border-b border-gray-100">
                  <td className="px-4 py-2 font-medium">{s.firm_name}</td>
                  <td className="px-4 py-2 text-gray-600">{s.plan ?? '—'}</td>
                  <td className="px-4 py-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${SUB_STATUS_COLOR[s.status] ?? 'bg-gray-100 text-gray-600'}`}>
                      {s.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-500">{s.provider ?? '—'}</td>
                  <td className="px-4 py-2 text-gray-500">
                    {s.current_period_end ? new Date(s.current_period_end).toLocaleDateString('ar-EG') : '—'}
                  </td>
                  <td className="px-4 py-2 text-left">
                    <button
                      onClick={() => setManualPayment(s)}
                      className="rounded border border-green-200 bg-green-50 px-2 py-1 text-xs text-green-700 hover:bg-green-100"
                    >
                      دفعة يدوية
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && subs.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-6 text-center text-gray-400">لا توجد اشتراكات</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Events tab */}
      {tab === 'events' && (
        <>
          <label className="mb-3 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={unprocessedOnly} onChange={e => setUnprocessedOnly(e.target.checked)} />
            عرض غير المعالجة فقط
          </label>
          <div className="overflow-x-auto rounded border border-gray-200 bg-white">
            <table className="w-full text-sm">
              <thead className="border-b border-gray-200 bg-gray-50 text-right">
                <tr>
                  <th className="px-4 py-2 font-medium">النوع</th>
                  <th className="px-4 py-2 font-medium">المرجع</th>
                  <th className="px-4 py-2 font-medium">المبلغ</th>
                  <th className="px-4 py-2 font-medium">التاريخ</th>
                  <th className="px-4 py-2 font-medium">الحالة</th>
                  <th className="px-4 py-2 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={6} className="px-4 py-6 text-center text-gray-400">جارٍ التحميل…</td></tr>
                )}
                {!loading && events.map((ev) => (
                  <tr key={ev.id} className="border-b border-gray-100">
                    <td className="px-4 py-2">{ev.event_type}</td>
                    <td className="px-4 py-2 font-mono text-xs text-gray-500">{ev.provider_ref ?? '—'}</td>
                    <td className="px-4 py-2 text-gray-600">
                      {ev.amount_cents != null ? `${(ev.amount_cents / 100).toFixed(2)} جنيه` : '—'}
                    </td>
                    <td className="px-4 py-2 text-gray-500">
                      {new Date(ev.created_at).toLocaleDateString('ar-EG')}
                    </td>
                    <td className="px-4 py-2">
                      {ev.resolved ? (
                        <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700">معالج</span>
                      ) : (
                        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
                          {ev.processed_at ? 'محدد' : 'معلّق'}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex gap-1">
                        {ev.payload && (
                          <button
                            onClick={() => setPayloadEvent(ev)}
                            className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
                          >
                            البيانات
                          </button>
                        )}
                        {!ev.resolved && (
                          <button
                            onClick={() => setResolveEvent(ev)}
                            className="rounded border border-blue-200 bg-blue-50 px-2 py-1 text-xs text-blue-700 hover:bg-blue-100"
                          >
                            معالجة
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {!loading && events.length === 0 && (
                  <tr><td colSpan={6} className="px-4 py-6 text-center text-gray-400">لا توجد أحداث</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
