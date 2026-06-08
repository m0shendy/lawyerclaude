'use client'

// Appointment detail + edit.
// GET    /appointments/{id}   — load
// PATCH  /appointments/{id}   — save (reruns conflict check on the server)
// DELETE /appointments/{id}   — manager/creator only

import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ApiError, apiDelete, apiGet, apiPatch } from '@/lib/api'
import { ALL_ROLES, RequireRole, useUser } from '@/lib/rbac'
import {
  APPOINTMENT_STATUS_COLORS,
  APPOINTMENT_STATUS_LABELS,
  APPOINTMENT_TYPE_LABELS,
  type Appointment,
  type AppointmentStatus,
  type AppointmentType,
  type Case,
  type User,
} from '@/lib/types'

const TYPE_OPTS = Object.keys(APPOINTMENT_TYPE_LABELS) as AppointmentType[]
const STATUS_OPTS = Object.keys(APPOINTMENT_STATUS_LABELS) as AppointmentStatus[]

function fmt(iso: string) {
  return new Date(iso).toLocaleString('ar-EG', {
    year: 'numeric', month: 'long', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function toLocalInput(iso: string) {
  // Convert ISO to datetime-local input value (YYYY-MM-DDTHH:mm)
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export default function AppointmentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { user } = useUser()

  const [appt, setAppt] = useState<Appointment | null>(null)
  const [lawyers, setLawyers] = useState<User[]>([])
  const [cases, setCases] = useState<Case[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)

  // Edit form state
  const [type, setType] = useState<AppointmentType>('consultation')
  const [lawyerId, setLawyerId] = useState('')
  const [caseId, setCaseId] = useState('')
  const [scheduledAt, setScheduledAt] = useState('')
  const [duration, setDuration] = useState(60)
  const [status, setStatus] = useState<AppointmentStatus>('scheduled')
  const [reason, setReason] = useState('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [saveErr, setSaveErr] = useState<string | null>(null)
  const [conflict, setConflict] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setErr(null)
    try {
      const a = await apiGet<Appointment>(`/appointments/${id}`)
      setAppt(a)
      setType(a.type)
      setLawyerId(a.assigned_lawyer_id)
      setCaseId(a.case_id ?? '')
      setScheduledAt(toLocalInput(a.scheduled_at))
      setDuration(a.duration_minutes)
      setStatus(a.status)
      setReason(a.reason ?? '')
      setNotes(a.notes ?? '')
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'تعذّر تحميل الموعد')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    apiGet<User[]>('/users')
      .then(us => setLawyers(us.filter(u => u.role === 'lawyer' || u.role === 'partner_manager')))
      .catch(() => setLawyers([]))
    apiGet<Case[]>('/cases').then(setCases).catch(() => setCases([]))
  }, [])

  async function save(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setSaveErr(null)
    setConflict(null)
    try {
      await apiPatch(`/appointments/${id}`, {
        type,
        assigned_lawyer_id: lawyerId,
        case_id: caseId || null,
        scheduled_at: new Date(scheduledAt).toISOString(),
        duration_minutes: duration,
        status,
        reason: reason || null,
        notes: notes || null,
      })
      setEditing(false)
      load()
    } catch (e) {
      if (e instanceof ApiError && e.code === 'appointment_time_conflict') {
        setConflict(e.message)
      } else {
        setSaveErr(e instanceof ApiError ? e.message : 'تعذّر الحفظ')
      }
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!confirm('هل تريد حذف هذا الموعد؟')) return
    try {
      await apiDelete(`/appointments/${id}`)
      router.push('/appointments')
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'تعذّر الحذف')
    }
  }

  const canEdit = user?.role === 'partner_manager' || user?.role === 'lawyer' ||
    user?.role === 'secretary' || appt?.created_by === user?.id

  const lawyerName = (lid: string) => lawyers.find(u => u.id === lid)?.full_name ?? lid.slice(0, 8)
  const caseName = (cid: string) => {
    const c = cases.find(c => c.id === cid)
    return c ? `${c.case_number ? c.case_number + ' — ' : ''}${c.title}` : cid.slice(0, 8)
  }

  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        {/* Breadcrumb */}
        <div className="mb-6 flex items-center gap-2 text-sm text-gray-500">
          <Link href="/appointments" className="hover:text-gray-700">المواعيد</Link>
          <span>/</span>
          <span className="text-gray-800">{loading ? '…' : 'تفاصيل الموعد'}</span>
        </div>

        {err && (
          <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{err}</div>
        )}

        {loading ? (
          <p className="text-sm text-gray-500">جارٍ التحميل…</p>
        ) : appt ? (
          <>
            {/* Header */}
            <div className="mb-6 flex items-start justify-between gap-4">
              <div>
                <h1 className="text-xl font-bold">{APPOINTMENT_TYPE_LABELS[appt.type]}</h1>
                <p className="mt-0.5 text-sm text-gray-500">{fmt(appt.scheduled_at)} · {appt.duration_minutes} دقيقة</p>
              </div>
              <div className="flex items-center gap-2">
                <span className={`rounded-full px-3 py-1 text-xs font-medium ${APPOINTMENT_STATUS_COLORS[appt.status]}`}>
                  {APPOINTMENT_STATUS_LABELS[appt.status]}
                </span>
                {canEdit && !editing && (
                  <button
                    onClick={() => setEditing(true)}
                    className="rounded-lg border border-gray-300 px-3 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
                  >
                    تعديل
                  </button>
                )}
                {(user?.role === 'partner_manager' || appt.created_by === user?.id) && (
                  <button
                    onClick={remove}
                    className="rounded-lg border border-red-200 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
                  >
                    حذف
                  </button>
                )}
              </div>
            </div>

            {/* Detail card */}
            <div className="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <dl className="grid grid-cols-1 gap-y-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="font-medium text-gray-500">المحامي المكلَّف</dt>
                  <dd className="mt-0.5 text-gray-900">{lawyerName(appt.assigned_lawyer_id)}</dd>
                </div>
                <div>
                  <dt className="font-medium text-gray-500">نوع الموعد</dt>
                  <dd className="mt-0.5 text-gray-900">{APPOINTMENT_TYPE_LABELS[appt.type]}</dd>
                </div>
                <div>
                  <dt className="font-medium text-gray-500">التاريخ والوقت</dt>
                  <dd className="mt-0.5 text-gray-900">{fmt(appt.scheduled_at)}</dd>
                </div>
                <div>
                  <dt className="font-medium text-gray-500">المدة</dt>
                  <dd className="mt-0.5 text-gray-900">{appt.duration_minutes} دقيقة</dd>
                </div>
                {appt.case_id && (
                  <div>
                    <dt className="font-medium text-gray-500">القضية</dt>
                    <dd className="mt-0.5">
                      <Link href={`/cases/${appt.case_id}`} className="text-blue-700 hover:underline">
                        {caseName(appt.case_id)}
                      </Link>
                    </dd>
                  </div>
                )}
                {appt.reason && (
                  <div className="sm:col-span-2">
                    <dt className="font-medium text-gray-500">سبب الموعد</dt>
                    <dd className="mt-0.5 text-gray-900">{appt.reason}</dd>
                  </div>
                )}
                {appt.notes && (
                  <div className="sm:col-span-2">
                    <dt className="font-medium text-gray-500">ملاحظات</dt>
                    <dd className="mt-0.5 whitespace-pre-wrap text-gray-900">{appt.notes}</dd>
                  </div>
                )}
              </dl>
            </div>

            {/* Edit form */}
            {editing && (
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-5">
                <h2 className="mb-4 text-sm font-bold text-blue-800">تعديل الموعد</h2>
                <form onSubmit={save} className="space-y-4">
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    {/* Type */}
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-700">نوع الموعد</label>
                      <select
                        value={type}
                        onChange={e => setType(e.target.value as AppointmentType)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {TYPE_OPTS.map(t => (
                          <option key={t} value={t}>{APPOINTMENT_TYPE_LABELS[t]}</option>
                        ))}
                      </select>
                    </div>

                    {/* Status */}
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-700">الحالة</label>
                      <select
                        value={status}
                        onChange={e => setStatus(e.target.value as AppointmentStatus)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {STATUS_OPTS.map(s => (
                          <option key={s} value={s}>{APPOINTMENT_STATUS_LABELS[s]}</option>
                        ))}
                      </select>
                    </div>

                    {/* Lawyer */}
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-700">المحامي المكلَّف</label>
                      <select
                        value={lawyerId}
                        onChange={e => setLawyerId(e.target.value)}
                        required
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        <option value="">— اختر محامياً —</option>
                        {lawyers.map(u => (
                          <option key={u.id} value={u.id}>{u.full_name}</option>
                        ))}
                      </select>
                    </div>

                    {/* Case */}
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-700">القضية (اختياري)</label>
                      <select
                        value={caseId}
                        onChange={e => setCaseId(e.target.value)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        <option value="">— لا توجد قضية —</option>
                        {cases.map(c => (
                          <option key={c.id} value={c.id}>
                            {c.case_number ? `${c.case_number} — ` : ''}{c.title}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Date/time */}
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-700">التاريخ والوقت *</label>
                      <input
                        type="datetime-local"
                        value={scheduledAt}
                        onChange={e => setScheduledAt(e.target.value)}
                        required
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>

                    {/* Duration */}
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-700">المدة (دقيقة)</label>
                      <input
                        type="number"
                        value={duration}
                        min={15}
                        step={15}
                        onChange={e => setDuration(Number(e.target.value))}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>
                  </div>

                  {/* Reason */}
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-700">سبب الموعد</label>
                    <input
                      type="text"
                      value={reason}
                      onChange={e => setReason(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>

                  {/* Notes */}
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-700">ملاحظات</label>
                    <textarea
                      value={notes}
                      onChange={e => setNotes(e.target.value)}
                      rows={2}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>

                  {conflict && (
                    <div className="flex items-center gap-2 rounded border-2 border-red-400 bg-red-50 px-3 py-2 text-sm font-semibold text-red-800">
                      <span>⚠</span>
                      {conflict} — غيِّر الوقت أو المحامي ثم أعد المحاولة.
                    </div>
                  )}
                  {saveErr && <p className="text-xs text-red-700">{saveErr}</p>}

                  <div className="flex gap-2 pt-1">
                    <button
                      type="submit"
                      disabled={busy}
                      className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-50"
                    >
                      {busy ? 'جارٍ الحفظ…' : 'حفظ التعديلات'}
                    </button>
                    <button
                      type="button"
                      onClick={() => { setEditing(false); setConflict(null); setSaveErr(null) }}
                      className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                    >
                      إلغاء
                    </button>
                  </div>
                </form>
              </div>
            )}
          </>
        ) : null}
      </AppShell>
    </RequireRole>
  )
}
