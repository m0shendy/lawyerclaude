'use client'

// Appointments (spec 002 US7): list + create with inline conflict warning.
// A 409 appointment_time_conflict from the API is surfaced inline and the
// user must pick a different time before saving.

import { useCallback, useEffect, useState, type FormEvent } from 'react'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet, apiPatch, apiPost } from '@/lib/api'
import { ALL_ROLES, RequireRole } from '@/lib/rbac'
import {
  APPOINTMENT_STATUS_COLORS,
  APPOINTMENT_STATUS_LABELS,
  APPOINTMENT_TYPE_LABELS,
  type Appointment,
  type AppointmentStatus,
  type AppointmentType,
  type Case,
  type Contact,
  type User,
} from '@/lib/types'

const TYPE_OPTS = Object.keys(APPOINTMENT_TYPE_LABELS) as AppointmentType[]
const STATUS_OPTS = Object.keys(APPOINTMENT_STATUS_LABELS) as AppointmentStatus[]

function NewAppointmentForm({
  lawyers,
  cases,
  contacts,
  onCreated,
}: {
  lawyers: User[]
  cases: Case[]
  contacts: Contact[]
  onCreated: () => void
}) {
  const [type, setType] = useState<AppointmentType>('consultation')
  const [lawyerId, setLawyerId] = useState('')
  const [caseId, setCaseId] = useState('')
  const [contactId, setContactId] = useState('')
  const [scheduledAt, setScheduledAt] = useState('')
  const [duration, setDuration] = useState(60)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [conflict, setConflict] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!lawyerId || !scheduledAt) return
    setBusy(true)
    setConflict(null)
    setErr(null)
    setOk(false)
    try {
      await apiPost('/appointments', {
        type,
        assigned_lawyer_id: lawyerId,
        case_id: caseId || null,
        contact_id: contactId || null,
        scheduled_at: new Date(scheduledAt).toISOString(),
        duration_minutes: duration,
        reason: reason || null,
      })
      setOk(true)
      setScheduledAt('')
      setReason('')
      onCreated()
    } catch (e) {
      if (e instanceof ApiError && e.code === 'appointment_time_conflict') {
        // تعارض حجز — يجب اختيار وقت آخر قبل الحفظ
        setConflict(e.message)
      } else {
        setErr(e instanceof ApiError ? e.message : 'تعذّر إنشاء الموعد')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      onSubmit={submit}
      className="mb-6 grid grid-cols-1 gap-3 rounded-xl border border-gray-200 bg-white p-5 shadow-sm sm:grid-cols-3"
    >
      <h2 className="font-semibold sm:col-span-3">موعد جديد</h2>

      <label className="text-sm">
        النوع
        <select
          value={type}
          onChange={(e) => setType(e.target.value as AppointmentType)}
          className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5"
        >
          {TYPE_OPTS.map((t) => (
            <option key={t} value={t}>
              {APPOINTMENT_TYPE_LABELS[t]}
            </option>
          ))}
        </select>
      </label>

      <label className="text-sm">
        المحامي *
        <select
          value={lawyerId}
          onChange={(e) => {
            setLawyerId(e.target.value)
            setConflict(null)
          }}
          required
          className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5"
        >
          <option value="">— اختر —</option>
          {lawyers.map((u) => (
            <option key={u.id} value={u.id}>
              {u.full_name}
            </option>
          ))}
        </select>
      </label>

      <label className="text-sm">
        الموعد *
        <input
          type="datetime-local"
          value={scheduledAt}
          onChange={(e) => {
            setScheduledAt(e.target.value)
            setConflict(null)
          }}
          required
          className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5"
        />
      </label>

      <label className="text-sm">
        المدة (دقيقة)
        <input
          type="number"
          min={15}
          step={15}
          value={duration}
          onChange={(e) => {
            setDuration(Number(e.target.value))
            setConflict(null)
          }}
          className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5"
        />
      </label>

      <label className="text-sm">
        القضية (اختياري)
        <select
          value={caseId}
          onChange={(e) => setCaseId(e.target.value)}
          className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5"
        >
          <option value="">— بدون —</option>
          {cases.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </select>
      </label>

      <label className="text-sm">
        العميل (اختياري)
        <select
          value={contactId}
          onChange={(e) => setContactId(e.target.value)}
          className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5"
        >
          <option value="">— بدون —</option>
          {contacts.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name_ar}
            </option>
          ))}
        </select>
      </label>

      <label className="text-sm sm:col-span-2">
        السبب
        <input
          type="text"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5"
        />
      </label>

      <div className="flex items-end">
        <button
          type="submit"
          disabled={busy || conflict !== null}
          className="rounded bg-blue-700 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
        >
          {busy ? 'جارٍ الحفظ…' : 'حفظ الموعد'}
        </button>
      </div>

      {conflict && (
        <div className="flex items-center gap-2 rounded border-2 border-red-400 bg-red-50 px-3 py-2 text-sm font-semibold text-red-800 sm:col-span-3">
          <span aria-hidden>⚠</span>
          {conflict} — غيِّر الوقت أو المحامي ثم أعد المحاولة.
        </div>
      )}
      {err && <p className="text-sm text-red-700 sm:col-span-3">{err}</p>}
      {ok && <p className="text-sm text-green-700 sm:col-span-3">✓ تم إنشاء الموعد</p>}
    </form>
  )
}

function AppointmentsScreen() {
  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [lawyers, setLawyers] = useState<User[]>([])
  const [cases, setCases] = useState<Case[]>([])
  const [contacts, setContacts] = useState<Contact[]>([])
  const [statusFilter, setStatusFilter] = useState<AppointmentStatus | ''>('')
  const [lawyerFilter, setLawyerFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const lawyerName = (id: string) => lawyers.find((u) => u.id === id)?.full_name ?? '—'

  const reload = useCallback(() => {
    const params = new URLSearchParams()
    if (statusFilter) params.set('status', statusFilter)
    if (lawyerFilter) params.set('lawyer_id', lawyerFilter)
    const q = params.toString() ? `?${params}` : ''
    setLoading(true)
    apiGet<Appointment[]>(`/appointments${q}`)
      .then(setAppointments)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'حدث خطأ'))
      .finally(() => setLoading(false))
  }, [statusFilter, lawyerFilter])

  useEffect(() => {
    reload()
  }, [reload])

  useEffect(() => {
    apiGet<User[]>('/users')
      .then((us) => setLawyers(us.filter((u) => u.status === 'active')))
      .catch(() => setLawyers([]))
    apiGet<Case[]>('/cases').then(setCases).catch(() => setCases([]))
    apiGet<Contact[]>('/contacts?type=client').then(setContacts).catch(() => setContacts([]))
  }, [])

  async function setStatus(id: string, status: AppointmentStatus) {
    try {
      await apiPatch(`/appointments/${id}`, { status })
      reload()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'تعذّر تحديث الموعد')
    }
  }

  return (
    <>
      <h1 className="mb-4 text-xl font-bold">المواعيد</h1>

      <NewAppointmentForm
        lawyers={lawyers}
        cases={cases}
        contacts={contacts}
        onCreated={reload}
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as AppointmentStatus | '')}
          className="rounded border border-gray-300 px-2 py-1.5 text-sm"
        >
          <option value="">كل الحالات</option>
          {STATUS_OPTS.map((s) => (
            <option key={s} value={s}>
              {APPOINTMENT_STATUS_LABELS[s]}
            </option>
          ))}
        </select>
        <select
          value={lawyerFilter}
          onChange={(e) => setLawyerFilter(e.target.value)}
          className="rounded border border-gray-300 px-2 py-1.5 text-sm"
        >
          <option value="">كل المحامين</option>
          {lawyers.map((u) => (
            <option key={u.id} value={u.id}>
              {u.full_name}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-300 bg-red-50 px-4 py-3 text-red-800">
          {error}
        </div>
      )}

      {loading ? (
        <p className="p-8 text-center text-gray-500">جارٍ التحميل…</p>
      ) : appointments.length === 0 ? (
        <p className="p-8 text-center text-gray-500">لا توجد مواعيد</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-right text-xs text-gray-500">
              <tr>
                <th className="px-4 py-2">الموعد</th>
                <th className="px-4 py-2">النوع</th>
                <th className="px-4 py-2">المحامي</th>
                <th className="px-4 py-2">المدة</th>
                <th className="px-4 py-2">السبب</th>
                <th className="px-4 py-2">الحالة</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {appointments.map((a) => (
                <tr key={a.id} className="border-t border-gray-100">
                  <td className="px-4 py-2 whitespace-nowrap">
                    {new Date(a.scheduled_at).toLocaleString('ar-EG')}
                  </td>
                  <td className="px-4 py-2">{APPOINTMENT_TYPE_LABELS[a.type]}</td>
                  <td className="px-4 py-2">{lawyerName(a.assigned_lawyer_id)}</td>
                  <td className="px-4 py-2">{a.duration_minutes} د</td>
                  <td className="px-4 py-2">{a.reason ?? '—'}</td>
                  <td className="px-4 py-2">
                    <span
                      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${APPOINTMENT_STATUS_COLORS[a.status]}`}
                    >
                      {APPOINTMENT_STATUS_LABELS[a.status]}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    {a.status === 'scheduled' && (
                      <button
                        type="button"
                        onClick={() => void setStatus(a.id, 'confirmed')}
                        className="text-xs text-blue-700 hover:underline"
                      >
                        تأكيد
                      </button>
                    )}
                    {(a.status === 'scheduled' || a.status === 'confirmed') && (
                      <button
                        type="button"
                        onClick={() => void setStatus(a.id, 'cancelled')}
                        className="mr-3 text-xs text-red-700 hover:underline"
                      >
                        إلغاء
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

export default function AppointmentsPage() {
  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <AppointmentsScreen />
      </AppShell>
    </RequireRole>
  )
}
