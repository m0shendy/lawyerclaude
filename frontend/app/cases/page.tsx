'use client'

// T038 — Cases list (all roles, server-scoped: manager sees all, others see
// assigned cases only). "New case" form is shown to manager/lawyer only —
// the server enforces the same rule on POST /cases. [C-I][C-III]

import { useEffect, useState, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import AppShell from '@/components/AppShell'
import ConflictCheckPanel from '@/components/ConflictCheckPanel'
import { ApiError, apiGet, apiPost } from '@/lib/api'
import { ALL_ROLES, RequireRole, useUser } from '@/lib/rbac'
import {
  CASE_STAGE_LABELS,
  PRIORITY_COLORS,
  PRIORITY_LABELS,
  type Case,
  type CaseStage,
  type Priority,
} from '@/lib/types'

const CASE_STATUS_LABELS: Record<string, string> = {
  open: 'مفتوحة',
  closed: 'مغلقة',
  suspended: 'معلّقة',
}

function statusLabel(status: string): string {
  return CASE_STATUS_LABELS[status] ?? status
}

function NewCaseForm({ onCreated }: { onCreated: (c: Case) => void }) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [clientName, setClientName] = useState('')
  const [caseNumber, setCaseNumber] = useState('')
  const [court, setCourt] = useState('')
  const [caseType, setCaseType] = useState('')
  // spec 002 matter extensions
  const [practiceArea, setPracticeArea] = useState('')
  const [jurisdiction, setJurisdiction] = useState('')
  const [opposingCounsel, setOpposingCounsel] = useState('')
  const [docketNumber, setDocketNumber] = useState('')
  const [tags, setTags] = useState('')
  const [priority, setPriority] = useState<Priority>('medium')
  const [stage, setStage] = useState<CaseStage>('intake')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const created = await apiPost<Case>('/cases', {
        title,
        client_name: clientName,
        case_number: caseNumber || null,
        court: court || null,
        case_type: caseType || null,
        practice_area: practiceArea || null,
        jurisdiction: jurisdiction || null,
        opposing_counsel: opposingCounsel || null,
        docket_number: docketNumber || null,
        tags: tags.split(',').map((t) => t.trim()).filter(Boolean),
        priority,
        stage,
      })
      onCreated(created)
      setTitle('')
      setClientName('')
      setCaseNumber('')
      setCourt('')
      setCaseType('')
      setPracticeArea('')
      setJurisdiction('')
      setOpposingCounsel('')
      setDocketNumber('')
      setTags('')
      setPriority('medium')
      setStage('intake')
      setOpen(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'حدث خطأ غير متوقع')
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="rounded bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800"
      >
        + قضية جديدة
      </button>
    )
  }

  const field = 'w-full rounded border border-gray-300 px-3 py-2 text-sm'

  return (
    <form
      onSubmit={onSubmit}
      className="mb-4 w-full rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
    >
      <h2 className="mb-3 font-semibold">قضية جديدة</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="nc-title">
            عنوان القضية *
          </label>
          <input
            id="nc-title"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className={field}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="nc-client">
            اسم الموكّل *
          </label>
          <input
            id="nc-client"
            required
            value={clientName}
            onChange={(e) => setClientName(e.target.value)}
            className={field}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="nc-number">
            رقم القضية
          </label>
          <input
            id="nc-number"
            value={caseNumber}
            onChange={(e) => setCaseNumber(e.target.value)}
            className={field}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="nc-court">
            المحكمة
          </label>
          <input
            id="nc-court"
            value={court}
            onChange={(e) => setCourt(e.target.value)}
            className={field}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="nc-type">
            نوع القضية
          </label>
          <input
            id="nc-type"
            value={caseType}
            onChange={(e) => setCaseType(e.target.value)}
            className={field}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="nc-practice">
            مجال الممارسة
          </label>
          <input
            id="nc-practice"
            value={practiceArea}
            onChange={(e) => setPracticeArea(e.target.value)}
            placeholder="مدني، تجاري، عمالي…"
            className={field}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="nc-jurisdiction">
            الاختصاص
          </label>
          <input
            id="nc-jurisdiction"
            value={jurisdiction}
            onChange={(e) => setJurisdiction(e.target.value)}
            className={field}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="nc-docket">
            رقم الدائرة / الجدول
          </label>
          <input
            id="nc-docket"
            value={docketNumber}
            onChange={(e) => setDocketNumber(e.target.value)}
            className={field}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="nc-tags">
            وسوم (مفصولة بفاصلة)
          </label>
          <input
            id="nc-tags"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            className={field}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="nc-priority">
            الأولوية
          </label>
          <select
            id="nc-priority"
            value={priority}
            onChange={(e) => setPriority(e.target.value as Priority)}
            className={field}
          >
            {(Object.keys(PRIORITY_LABELS) as Priority[]).map((p) => (
              <option key={p} value={p}>
                {PRIORITY_LABELS[p]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="nc-stage">
            المرحلة
          </label>
          <select
            id="nc-stage"
            value={stage}
            onChange={(e) => setStage(e.target.value as CaseStage)}
            className={field}
          >
            {(Object.keys(CASE_STAGE_LABELS) as CaseStage[]).map((s) => (
              <option key={s} value={s}>
                {CASE_STAGE_LABELS[s]}
              </option>
            ))}
          </select>
        </div>
        <div className="sm:col-span-2">
          <label className="mb-1 block text-sm font-medium" htmlFor="nc-opposing">
            محامي الخصم
          </label>
          <input
            id="nc-opposing"
            value={opposingCounsel}
            onChange={(e) => setOpposingCounsel(e.target.value)}
            className={field}
          />
          {opposingCounsel.trim() && (
            <div className="mt-2">
              <ConflictCheckPanel partyName={opposingCounsel} />
            </div>
          )}
        </div>
      </div>

      {error && <p className="mt-3 text-sm text-red-700">{error}</p>}

      <div className="mt-4 flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
        >
          {busy ? 'جارٍ الحفظ…' : 'حفظ'}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50"
        >
          إلغاء
        </button>
      </div>
    </form>
  )
}

function CasesContent() {
  const router = useRouter()
  const { user } = useUser()
  const [cases, setCases] = useState<Case[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filterPriority, setFilterPriority] = useState<Priority | ''>('')
  const [filterStage, setFilterStage] = useState<CaseStage | ''>('')

  const canCreate = user?.role === 'partner_manager' || user?.role === 'lawyer'

  useEffect(() => {
    apiGet<Case[]>('/cases')
      .then(setCases)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'تعذّر تحميل القضايا'),
      )
  }, [])

  const visible = (cases ?? []).filter((c) => {
    if (filterPriority && c.priority !== filterPriority) return false
    if (filterStage && c.stage !== filterStage) return false
    return true
  })

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-bold">القضايا</h1>
        {canCreate && cases !== null && (
          <NewCaseForm onCreated={(c) => setCases((prev) => [c, ...(prev ?? [])])} />
        )}
      </div>

      {error && (
        <p className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}

      {!error && cases === null && (
        <p className="p-8 text-center text-gray-500">جارٍ التحميل…</p>
      )}

      {cases !== null && (
        <>
          <div className="mb-3 flex flex-wrap gap-2">
            <select
              value={filterPriority}
              onChange={(e) => setFilterPriority(e.target.value as Priority | '')}
              className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm"
            >
              <option value="">كل الأولويات</option>
              {(Object.keys(PRIORITY_LABELS) as Priority[]).map((p) => (
                <option key={p} value={p}>{PRIORITY_LABELS[p]}</option>
              ))}
            </select>
            <select
              value={filterStage}
              onChange={(e) => setFilterStage(e.target.value as CaseStage | '')}
              className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm"
            >
              <option value="">كل المراحل</option>
              {(Object.keys(CASE_STAGE_LABELS) as CaseStage[]).map((s) => (
                <option key={s} value={s}>{CASE_STAGE_LABELS[s]}</option>
              ))}
            </select>
            {(filterPriority || filterStage) && (
              <button
                type="button"
                onClick={() => { setFilterPriority(''); setFilterStage('') }}
                className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
              >
                مسح الفلاتر
              </button>
            )}
          </div>

          {visible.length === 0 ? (
            <p className="rounded border border-gray-200 bg-white p-8 text-center text-gray-500">
              {cases.length === 0
                ? 'لا توجد قضايا ضمن نطاق صلاحياتك بعد'
                : 'لا توجد قضايا تطابق الفلاتر المحددة'}
            </p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50 text-right text-gray-600">
                    <th className="px-4 py-3 font-medium">العنوان</th>
                    <th className="px-4 py-3 font-medium">الموكّل</th>
                    <th className="px-4 py-3 font-medium">رقم القضية</th>
                    <th className="px-4 py-3 font-medium">المحكمة</th>
                    <th className="px-4 py-3 font-medium">الأولوية</th>
                    <th className="px-4 py-3 font-medium">المرحلة</th>
                    <th className="px-4 py-3 font-medium">الحالة</th>
                    <th className="px-4 py-3 font-medium">تاريخ الإنشاء</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((c) => (
                    <tr
                      key={c.id}
                      onClick={() => router.push(`/cases/${c.id}`)}
                      className="cursor-pointer border-b border-gray-100 last:border-0 hover:bg-blue-50"
                    >
                      <td className="px-4 py-3 font-semibold text-blue-800">{c.title}</td>
                      <td className="px-4 py-3">{c.client_name}</td>
                      <td className="px-4 py-3" dir="ltr">
                        {c.case_number ?? '—'}
                      </td>
                      <td className="px-4 py-3">{c.court ?? '—'}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${PRIORITY_COLORS[c.priority ?? 'medium']}`}>
                          {PRIORITY_LABELS[c.priority ?? 'medium']}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded bg-blue-50 px-2 py-0.5 text-xs text-blue-800">
                          {CASE_STAGE_LABELS[c.stage as CaseStage] ?? c.stage ?? '—'}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded bg-gray-100 px-2 py-0.5 text-xs">
                          {statusLabel(c.status)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-500">
                        {new Date(c.created_at).toLocaleDateString('ar-EG')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default function CasesPage() {
  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <CasesContent />
      </AppShell>
    </RequireRole>
  )
}
