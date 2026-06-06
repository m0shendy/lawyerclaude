'use client'

// T038 — Case detail (assigned users / manager; the server scopes access).
// Inline edit: manager or assigned lawyer. Delete: manager only (confirmed).
// Sections: assignments (assign/unassign), documents, deadlines, tasks,
// AI outputs (review_state + low-confidence badges → /ai-review). [C-I][C-III]

import { useCallback, useEffect, useState, type FormEvent } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import AppShell from '@/components/AppShell'
import { ApiError, apiDelete, apiGet, apiPatch, apiPost } from '@/lib/api'
import { ALL_ROLES, RequireRole, useUser } from '@/lib/rbac'
import {
  DOCUMENT_STATUS_LABELS,
  ROLE_LABELS,
  type AiOutputType,
  type Case,
  type CaseAssignment,
  type Deadline,
  type Document,
  type ReviewState,
  type Role,
  type TaskItem,
  type User,
} from '@/lib/types'

// ── case-detail response type (mirrors backend CaseDetail) ──────────────────

interface AiOutputSummary {
  id: string
  type: AiOutputType
  review_state: ReviewState
  low_confidence_flag: boolean
  created_at: string
}

interface AssignmentWithUser extends CaseAssignment {
  full_name: string
  role: Role
}

interface CaseDetail extends Case {
  documents: Document[]
  ai_outputs: AiOutputSummary[]
  deadlines: Deadline[]
  tasks: TaskItem[]
  assignments: AssignmentWithUser[]
}

// ── labels ───────────────────────────────────────────────────────────────────

const CASE_STATUS_LABELS: Record<string, string> = {
  open: 'مفتوحة',
  closed: 'مغلقة',
  suspended: 'معلّقة',
}

const AI_TYPE_LABELS: Record<AiOutputType, string> = {
  summary: 'ملخّص',
  extraction: 'استخراج بيانات',
  analysis: 'تحليل',
  clause_flag: 'تنبيه بند',
  risk_signal: 'إشارة مخاطرة',
}

const DEADLINE_TYPE_LABELS: Record<Deadline['type'], string> = {
  general: 'عام',
  appeal_istinaf: 'استئناف',
  mu_arada: 'معارضة',
  naqd: 'نقض',
}

const TASK_STATUS_LABELS: Record<TaskItem['status'], string> = {
  open: 'مفتوحة',
  in_progress: 'قيد التنفيذ',
  done: 'منجزة',
  cancelled: 'ملغاة',
}

const fmtDate = (iso: string) => new Date(iso).toLocaleDateString('ar-EG')

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 font-semibold">{title}</h2>
      {children}
    </section>
  )
}

// ── case fields with inline edit ─────────────────────────────────────────────

function CaseFields({
  detail,
  canEdit,
  onSaved,
}: {
  detail: CaseDetail
  canEdit: boolean
  onSaved: (c: Case) => void
}) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({
    title: detail.title,
    client_name: detail.client_name,
    case_number: detail.case_number ?? '',
    court: detail.court ?? '',
    case_type: detail.case_type ?? '',
    status: detail.status,
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function startEdit() {
    setForm({
      title: detail.title,
      client_name: detail.client_name,
      case_number: detail.case_number ?? '',
      court: detail.court ?? '',
      case_type: detail.case_type ?? '',
      status: detail.status,
    })
    setError(null)
    setEditing(true)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const updated = await apiPatch<Case>(`/cases/${detail.id}`, {
        title: form.title,
        client_name: form.client_name,
        case_number: form.case_number || null,
        court: form.court || null,
        case_type: form.case_type || null,
        status: form.status,
      })
      onSaved(updated)
      setEditing(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر حفظ التعديلات')
    } finally {
      setBusy(false)
    }
  }

  const field = 'w-full rounded border border-gray-300 px-3 py-2 text-sm'

  if (editing) {
    return (
      <form onSubmit={onSubmit} className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-sm font-medium">عنوان القضية *</label>
          <input
            required
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            className={field}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">اسم الموكّل *</label>
          <input
            required
            value={form.client_name}
            onChange={(e) => setForm({ ...form, client_name: e.target.value })}
            className={field}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">رقم القضية</label>
          <input
            value={form.case_number}
            onChange={(e) => setForm({ ...form, case_number: e.target.value })}
            className={field}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">المحكمة</label>
          <input
            value={form.court}
            onChange={(e) => setForm({ ...form, court: e.target.value })}
            className={field}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">نوع القضية</label>
          <input
            value={form.case_type}
            onChange={(e) => setForm({ ...form, case_type: e.target.value })}
            className={field}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">الحالة</label>
          <select
            value={form.status}
            onChange={(e) => setForm({ ...form, status: e.target.value })}
            className={field}
          >
            {Object.entries(CASE_STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        {error && <p className="text-sm text-red-700 sm:col-span-2">{error}</p>}

        <div className="flex gap-2 sm:col-span-2">
          <button
            type="submit"
            disabled={busy}
            className="rounded bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
          >
            {busy ? 'جارٍ الحفظ…' : 'حفظ'}
          </button>
          <button
            type="button"
            onClick={() => setEditing(false)}
            className="rounded border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
          >
            إلغاء
          </button>
        </div>
      </form>
    )
  }

  const rows: Array<[string, React.ReactNode]> = [
    ['اسم الموكّل', detail.client_name],
    ['رقم القضية', detail.case_number ? <span dir="ltr">{detail.case_number}</span> : '—'],
    ['المحكمة', detail.court ?? '—'],
    ['نوع القضية', detail.case_type ?? '—'],
    ['الحالة', CASE_STATUS_LABELS[detail.status] ?? detail.status],
    ['تاريخ الإنشاء', fmtDate(detail.created_at)],
  ]

  return (
    <div>
      <dl className="grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="flex gap-2">
            <dt className="w-28 shrink-0 text-gray-500">{label}</dt>
            <dd className="font-medium">{value}</dd>
          </div>
        ))}
      </dl>
      {canEdit && (
        <button
          onClick={startEdit}
          className="mt-4 rounded border border-blue-700 px-4 py-1.5 text-sm font-semibold text-blue-700 hover:bg-blue-50"
        >
          تعديل البيانات
        </button>
      )}
    </div>
  )
}

// ── assignments ───────────────────────────────────────────────────────────────

function AssignmentsSection({
  detail,
  canManage,
  isManager,
  onChanged,
}: {
  detail: CaseDetail
  canManage: boolean
  isManager: boolean
  onChanged: () => void
}) {
  const [users, setUsers] = useState<User[] | null>(null)
  const [usersError, setUsersError] = useState<string | null>(null)
  const [selected, setSelected] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!canManage) return
    apiGet<User[]>('/users')
      .then(setUsers)
      .catch((err) =>
        setUsersError(err instanceof ApiError ? err.message : 'تعذّر تحميل المستخدمين'),
      )
  }, [canManage])

  const assignedIds = new Set(detail.assignments.map((a) => a.user_id))
  const candidates = (users ?? []).filter(
    (u) => u.status === 'active' && !assignedIds.has(u.id),
  )

  async function assign(e: FormEvent) {
    e.preventDefault()
    if (!selected) return
    setError(null)
    setBusy(true)
    try {
      await apiPost(`/cases/${detail.id}/assignments`, { user_id: selected })
      setSelected('')
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر إسناد المستخدم')
    } finally {
      setBusy(false)
    }
  }

  async function unassign(userId: string) {
    setError(null)
    try {
      await apiDelete(`/cases/${detail.id}/assignments/${userId}`)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر إلغاء الإسناد')
    }
  }

  return (
    <Section title="المُسندون إلى القضية">
      {detail.assignments.length === 0 ? (
        <p className="text-sm text-gray-500">لا يوجد مستخدمون مُسندون بعد</p>
      ) : (
        <ul className="divide-y divide-gray-100 text-sm">
          {detail.assignments.map((a) => (
            <li key={a.id} className="flex items-center justify-between py-2">
              <span>
                <span className="font-medium">{a.full_name}</span>{' '}
                <span className="text-xs text-gray-500">({ROLE_LABELS[a.role]})</span>
              </span>
              {canManage && (
                <button
                  onClick={() => void unassign(a.user_id)}
                  className="rounded border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50"
                >
                  إلغاء الإسناد
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {canManage && (
        <form onSubmit={assign} className="mt-3 flex flex-wrap items-center gap-2">
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            className="rounded border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="">— اختر مستخدمًا —</option>
            {candidates.map((u) => (
              <option key={u.id} value={u.id}>
                {u.full_name} ({ROLE_LABELS[u.role]})
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={busy || !selected}
            className="rounded bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
          >
            {busy ? 'جارٍ الإسناد…' : 'إسناد'}
          </button>
          {usersError && isManager && (
            <span className="text-xs text-red-700">{usersError}</span>
          )}
        </form>
      )}

      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
    </Section>
  )
}

// ── main content ─────────────────────────────────────────────────────────────

function CaseDetailContent() {
  const params = useParams<{ id: string }>()
  const caseId = params.id
  const router = useRouter()
  const { user } = useUser()

  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(() => {
    apiGet<CaseDetail>(`/cases/${caseId}`)
      .then((d) => {
        setDetail(d)
        setError(null)
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'تعذّر تحميل القضية'),
      )
  }, [caseId])

  useEffect(() => {
    load()
  }, [load])

  const isManager = user?.role === 'partner_manager'
  const isAssignedLawyer =
    user?.role === 'lawyer' &&
    (detail?.assignments.some((a) => a.user_id === user.id) ?? false)
  const canEdit = isManager || isAssignedLawyer
  // The server allows manager or (accessing) lawyer to manage assignments.
  const canManageAssignments = isManager || isAssignedLawyer

  async function onDelete() {
    if (!detail) return
    if (!window.confirm(`هل أنت متأكد من حذف القضية «${detail.title}»؟ لا يمكن التراجع.`))
      return
    setDeleteError(null)
    setDeleting(true)
    try {
      await apiDelete(`/cases/${detail.id}`)
      router.replace('/cases')
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : 'تعذّر حذف القضية')
      setDeleting(false)
    }
  }

  if (error) {
    return (
      <div>
        <p className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
        <Link href="/cases" className="mt-3 inline-block text-sm text-blue-700 hover:underline">
          ← العودة إلى القضايا
        </Link>
      </div>
    )
  }

  if (!detail) {
    return <p className="p-8 text-center text-gray-500">جارٍ التحميل…</p>
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <Link href="/cases" className="text-sm text-blue-700 hover:underline">
            القضايا
          </Link>
          <h1 className="text-xl font-bold">{detail.title}</h1>
        </div>
        {isManager && (
          <button
            onClick={() => void onDelete()}
            disabled={deleting}
            className="rounded border border-red-600 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            {deleting ? 'جارٍ الحذف…' : 'حذف القضية'}
          </button>
        )}
      </div>
      {deleteError && <p className="mb-3 text-sm text-red-700">{deleteError}</p>}

      <Section title="بيانات القضية">
        <CaseFields
          detail={detail}
          canEdit={canEdit}
          onSaved={(c) => setDetail({ ...detail, ...c })}
        />
      </Section>

      <AssignmentsSection
        detail={detail}
        canManage={canManageAssignments}
        isManager={isManager}
        onChanged={load}
      />

      <Section title={`المستندات (${detail.documents.length})`}>
        {detail.documents.length === 0 ? (
          <p className="text-sm text-gray-500">لا توجد مستندات</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-right text-gray-600">
                <th className="py-2 font-medium">الملف</th>
                <th className="py-2 font-medium">الحالة</th>
                <th className="py-2 font-medium">دقّة المسح</th>
                <th className="py-2 font-medium">تاريخ الرفع</th>
              </tr>
            </thead>
            <tbody>
              {detail.documents.map((d) => (
                <tr key={d.id} className="border-b border-gray-100 last:border-0">
                  <td className="py-2">
                    <Link
                      href={`/documents/${d.id}`}
                      className="font-medium text-blue-700 hover:underline"
                    >
                      {d.file_name}
                    </Link>
                  </td>
                  <td className="py-2">
                    <span
                      className={`rounded px-2 py-0.5 text-xs ${
                        d.status === 'low_confidence' || d.status === 'failed'
                          ? 'bg-red-100 text-red-800'
                          : d.status === 'ready'
                            ? 'bg-green-100 text-green-800'
                            : 'bg-gray-100 text-gray-700'
                      }`}
                    >
                      {DOCUMENT_STATUS_LABELS[d.status]}
                    </span>
                  </td>
                  <td className="py-2" dir="ltr">
                    {d.ocr_confidence != null ? `${Math.round(d.ocr_confidence * 100)}%` : '—'}
                  </td>
                  <td className="py-2 text-gray-500">{fmtDate(d.uploaded_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title={`المواعيد والالتزامات (${detail.deadlines.length})`}>
        {detail.deadlines.length === 0 ? (
          <p className="text-sm text-gray-500">لا توجد مواعيد</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-right text-gray-600">
                <th className="py-2 font-medium">العنوان</th>
                <th className="py-2 font-medium">النوع</th>
                <th className="py-2 font-medium">تاريخ الاستحقاق</th>
                <th className="py-2 font-medium">الحالة</th>
              </tr>
            </thead>
            <tbody>
              {detail.deadlines.map((dl) => (
                <tr key={dl.id} className="border-b border-gray-100 last:border-0">
                  <td className="py-2 font-medium">{dl.title}</td>
                  <td className="py-2">{DEADLINE_TYPE_LABELS[dl.type]}</td>
                  <td className="py-2">{fmtDate(dl.due_date)}</td>
                  <td className="py-2">
                    {dl.type !== 'general' && !dl.confirmed ? (
                      <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
                        اقتراح بانتظار التأكيد
                      </span>
                    ) : (
                      <span className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-800">
                        مؤكَّد
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title={`المهام (${detail.tasks.length})`}>
        {detail.tasks.length === 0 ? (
          <p className="text-sm text-gray-500">لا توجد مهام</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-right text-gray-600">
                <th className="py-2 font-medium">الوصف</th>
                <th className="py-2 font-medium">تاريخ الاستحقاق</th>
                <th className="py-2 font-medium">الحالة</th>
              </tr>
            </thead>
            <tbody>
              {detail.tasks.map((t) => (
                <tr key={t.id} className="border-b border-gray-100 last:border-0">
                  <td className="py-2">{t.description}</td>
                  <td className="py-2">{t.due_date ? fmtDate(t.due_date) : '—'}</td>
                  <td className="py-2">
                    <span className="rounded bg-gray-100 px-2 py-0.5 text-xs">
                      {TASK_STATUS_LABELS[t.status]}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title={`مخرجات الذكاء الاصطناعي (${detail.ai_outputs.length})`}>
        {detail.ai_outputs.length === 0 ? (
          <p className="text-sm text-gray-500">لا توجد مخرجات</p>
        ) : (
          <ul className="divide-y divide-gray-100 text-sm">
            {detail.ai_outputs.map((o) => (
              <li key={o.id} className="flex flex-wrap items-center gap-2 py-2">
                <span className="font-medium">{AI_TYPE_LABELS[o.type]}</span>
                {o.review_state === 'approved' ? (
                  <span className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-800">
                    معتمَد
                  </span>
                ) : (
                  <span className="rounded bg-violet-100 px-2 py-0.5 text-xs text-violet-900">
                    بانتظار المراجعة
                  </span>
                )}
                {o.low_confidence_flag && (
                  <span className="rounded bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-800">
                    ⚠ جودة مسح منخفضة
                  </span>
                )}
                <span className="text-xs text-gray-500">{fmtDate(o.created_at)}</span>
                <Link
                  href="/ai-review"
                  className="ms-auto text-xs text-blue-700 hover:underline"
                >
                  فتح في شاشة المراجعة ←
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  )
}

export default function CaseDetailPage() {
  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <CaseDetailContent />
      </AppShell>
    </RequireRole>
  )
}
