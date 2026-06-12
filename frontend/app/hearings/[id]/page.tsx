'use client'

// Hearing detail + edit.
// GET  /hearings/{id}           — load
// PATCH /hearings/{id}          — save outcome / reschedule
// DELETE /hearings/{id}         — manager only

import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ApiError, apiDelete, apiGet, apiPatch } from '@/lib/api'
import { ALL_ROLES, RequireRole, useUser } from '@/lib/rbac'
import { HEARING_STATUS_COLORS, HEARING_STATUS_LABELS, type Hearing, type HearingStatus } from '@/lib/types'

const STATUS_OPTS: HearingStatus[] = ['scheduled', 'held', 'adjourned', 'cancelled']

function fmt(iso: string | null | undefined) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('ar-EG', {
    year: 'numeric', month: 'long', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function HearingDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { user } = useUser()

  const [hearing, setHearing] = useState<Hearing | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)

  // Edit form state
  const [status, setStatus] = useState<HearingStatus>('scheduled')
  const [result, setResult] = useState('')
  const [nextDate, setNextDate] = useState('')
  const [nextCourt, setNextCourt] = useState('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [saveErr, setSaveErr] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setErr(null)
    try {
      const h = await apiGet<Hearing>(`/hearings/${id}`)
      setHearing(h)
      setStatus(h.status)
      setResult(h.result ?? '')
      setNextDate(h.next_hearing_date ? h.next_hearing_date.slice(0, 16) : '')
      setNextCourt(h.next_hearing_court ?? '')
      setNotes(h.notes ?? '')
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'تعذّر تحميل الجلسة')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  async function save(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setSaveErr(null)
    try {
      await apiPatch(`/hearings/${id}`, {
        status,
        result: result || null,
        next_hearing_date: nextDate ? new Date(nextDate).toISOString() : null,
        next_hearing_court: nextCourt || null,
        notes: notes || null,
      })
      setEditing(false)
      load()
    } catch (e) {
      setSaveErr(e instanceof ApiError ? e.message : 'تعذّر الحفظ')
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!confirm('هل تريد حذف هذه الجلسة؟')) return
    try {
      await apiDelete(`/hearings/${id}`)
      router.push('/hearings')
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'تعذّر الحذف')
    }
  }

  const canEdit = user?.role === 'partner_manager' || user?.role === 'lawyer'

  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        {/* Breadcrumb */}
        <div className="mb-6 flex items-center gap-2 text-sm text-gray-500">
          <Link href="/hearings" className="hover:text-gray-700">الجلسات</Link>
          <span>/</span>
          <span className="text-gray-800">{loading ? '…' : 'تفاصيل الجلسة'}</span>
        </div>

        {err && (
          <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{err}</div>
        )}

        {loading ? (
          <p className="text-sm text-gray-500">جارٍ التحميل…</p>
        ) : hearing ? (
          <>
            {/* Header */}
            <div className="mb-6 flex items-start justify-between gap-4">
              <div>
                <h1 className="text-xl font-bold">{hearing.court_name}</h1>
                {hearing.court_room && (
                  <p className="text-sm text-gray-500 mt-0.5">قاعة {hearing.court_room}</p>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className={`rounded-full px-3 py-1 text-xs font-medium ${HEARING_STATUS_COLORS[hearing.status]}`}>
                  {HEARING_STATUS_LABELS[hearing.status]}
                </span>
                {canEdit && !editing && (
                  <button
                    onClick={() => setEditing(true)}
                    className="rounded-lg border border-gray-300 px-3 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
                  >
                    تعديل
                  </button>
                )}
                {user?.role === 'partner_manager' && (
                  <button
                    onClick={remove}
                    className="rounded-lg border border-red-200 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
                  >
                    حذف
                  </button>
                )}
              </div>
            </div>

            {/* Info card */}
            <div className="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <dl className="grid grid-cols-1 gap-y-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="font-medium text-gray-500">تاريخ الجلسة</dt>
                  <dd className="mt-0.5 text-gray-900">{fmt(hearing.hearing_date)}</dd>
                </div>
                <div>
                  <dt className="font-medium text-gray-500">القضية</dt>
                  <dd className="mt-0.5">
                    <Link href={`/cases/${hearing.case_id}`} className="text-blue-700 hover:underline">
                      عرض القضية
                    </Link>
                  </dd>
                </div>
                {hearing.result && (
                  <div className="sm:col-span-2">
                    <dt className="font-medium text-gray-500">نتيجة الجلسة</dt>
                    <dd className="mt-0.5 text-gray-900">{hearing.result}</dd>
                  </div>
                )}
                {hearing.next_hearing_date && (
                  <div>
                    <dt className="font-medium text-gray-500">الجلسة القادمة</dt>
                    <dd className="mt-0.5 text-gray-900">{fmt(hearing.next_hearing_date)}</dd>
                  </div>
                )}
                {hearing.next_hearing_court && (
                  <div>
                    <dt className="font-medium text-gray-500">محكمة الجلسة القادمة</dt>
                    <dd className="mt-0.5 text-gray-900">{hearing.next_hearing_court}</dd>
                  </div>
                )}
                {hearing.notes && (
                  <div className="sm:col-span-2">
                    <dt className="font-medium text-gray-500">ملاحظات</dt>
                    <dd className="mt-0.5 whitespace-pre-wrap text-gray-900">{hearing.notes}</dd>
                  </div>
                )}
              </dl>

              {/* Reminder flags */}
              <div className="mt-4 flex flex-wrap gap-2 pt-3 border-t border-gray-100">
                {(
                  [
                    { label: '7 أيام', sent: hearing.reminder_sent_7d },
                    { label: '3 أيام', sent: hearing.reminder_sent_3d },
                    { label: 'يوم واحد', sent: hearing.reminder_sent_1d },
                    { label: 'اليوم', sent: hearing.reminder_sent_0d },
                  ] as { label: string; sent: boolean }[]
                ).map(r => (
                  <span
                    key={r.label}
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      r.sent
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-500'
                    }`}
                  >
                    تذكير {r.label} {r.sent ? '✓' : '—'}
                  </span>
                ))}
              </div>
            </div>

            {/* Edit form */}
            {editing && (
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-5">
                <h2 className="mb-4 text-sm font-bold text-blue-800">تحديث الجلسة</h2>
                <form onSubmit={save} className="space-y-4">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-700">الحالة</label>
                    <select
                      value={status}
                      onChange={e => setStatus(e.target.value as HearingStatus)}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      {STATUS_OPTS.map(s => (
                        <option key={s} value={s}>{HEARING_STATUS_LABELS[s]}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-700">نتيجة الجلسة</label>
                    <textarea
                      value={result}
                      onChange={e => setResult(e.target.value)}
                      rows={2}
                      placeholder="مثال: تأجلت لجلسة الإثبات..."
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-700">تاريخ الجلسة القادمة</label>
                      <input
                        type="datetime-local"
                        value={nextDate}
                        onChange={e => setNextDate(e.target.value)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-700">محكمة الجلسة القادمة</label>
                      <input
                        type="text"
                        value={nextCourt}
                        onChange={e => setNextCourt(e.target.value)}
                        placeholder="نفس المحكمة..."
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-700">ملاحظات</label>
                    <textarea
                      value={notes}
                      onChange={e => setNotes(e.target.value)}
                      rows={2}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>

                  {saveErr && <p className="text-xs text-red-700">{saveErr}</p>}

                  <div className="flex gap-2">
                    <button
                      type="submit"
                      disabled={busy}
                      className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-50"
                    >
                      {busy ? 'جارٍ الحفظ…' : 'حفظ التحديث'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditing(false)}
                      className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                    >
                      إلغاء
                    </button>
                  </div>
                </form>
              </div>
            )}

            {/* Schedule next hearing shortcut */}
            {hearing.status === 'adjourned' && (
              <div className="mt-4">
                <Link
                  href={`/hearings/new?case_id=${hearing.case_id}`}
                  className="inline-flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-4 py-2 text-sm font-medium text-amber-800 hover:bg-amber-100"
                >
                  + جدولة جلسة بديلة لهذه القضية
                </Link>
              </div>
            )}
          </>
        ) : null}
      </AppShell>
    </RequireRole>
  )
}
