'use client'

// T069 — Deadlines & obligations screen (assigned/manager). [C-IV][C-X]
// General deadlines: CRUD by manager/assigned lawyer. Appeal-type deadlines
// arrive as confirm-required SUGGESTIONS (confirmed=false) and are inert until
// the responsible lawyer clicks "تأكيد" — reminders are fired only by the
// deterministic scheduler, never from this screen. [C-IV]

import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '@/components/AppShell'
import { ALL_ROLES, RequireRole, useUser } from '@/lib/rbac'
import { apiGet, apiPost, apiDelete, ApiError } from '@/lib/api'
import {
  DEADLINE_TYPE_LABELS,
  type Case,
  type Deadline,
  type Role,
} from '@/lib/types'

interface Assignment {
  id: string
  case_id: string
  user_id: string
  created_at: string
  full_name: string
  role: Role
}

interface CaseDetail extends Case {
  deadlines: Deadline[]
  assignments: Assignment[]
}

const CAN_EDIT: Role[] = ['partner_manager', 'lawyer']

function DeadlinesScreen() {
  const { user } = useUser()
  const canEdit = !!user && CAN_EDIT.includes(user.role)

  const [cases, setCases] = useState<Case[]>([])
  const [casesLoading, setCasesLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [selectedCaseId, setSelectedCaseId] = useState('')
  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // create form
  const [title, setTitle] = useState('')
  const [dueDate, setDueDate] = useState('')
  const [responsible, setResponsible] = useState('')
  const [basis, setBasis] = useState('')
  const [creating, setCreating] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    apiGet<Case[]>('/cases')
      .then((rows) => !cancelled && setCases(rows))
      .catch((err) =>
        !cancelled && setError(err instanceof ApiError ? err.message : 'تعذّر تحميل القضايا'),
      )
      .finally(() => !cancelled && setCasesLoading(false))
    return () => {
      cancelled = true
    }
  }, [])

  async function loadDetail(caseId: string) {
    if (!caseId) {
      setDetail(null)
      return
    }
    setDetailLoading(true)
    setError(null)
    try {
      const d = await apiGet<CaseDetail>(`/cases/${caseId}`)
      setDetail(d)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر تحميل المواعيد')
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    loadDetail(selectedCaseId)
    // reset form on case switch
    setResponsible('')
    setFormError(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCaseId])

  async function onCreate(e: FormEvent) {
    e.preventDefault()
    if (!selectedCaseId || !title || !dueDate || !responsible) return
    setFormError(null)
    setCreating(true)
    try {
      await apiPost<Deadline>(`/cases/${selectedCaseId}/deadlines`, {
        title,
        due_date: dueDate,
        responsible_user_id: responsible,
        basis: basis || null,
      })
      setTitle('')
      setDueDate('')
      setBasis('')
      await loadDetail(selectedCaseId)
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'تعذّر إنشاء الموعد')
    } finally {
      setCreating(false)
    }
  }

  async function onAcknowledge(id: string) {
    try {
      await apiPost(`/deadlines/${id}/acknowledge`)
      await loadDetail(selectedCaseId)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر تسجيل الإقرار')
    }
  }

  async function onConfirm(id: string) {
    try {
      await apiPost(`/deadlines/${id}/confirm`)
      await loadDetail(selectedCaseId)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر تأكيد الموعد')
    }
  }

  async function onDelete(id: string) {
    if (!confirm('حذف هذا الموعد؟')) return
    try {
      await apiDelete(`/deadlines/${id}`)
      await loadDetail(selectedCaseId)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر حذف الموعد')
    }
  }

  const nameOf = (userId: string) =>
    detail?.assignments.find((a) => a.user_id === userId)?.full_name ?? userId.slice(0, 8)

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="mb-6 text-2xl font-bold">المواعيد والالتزامات</h1>

      {error && (
        <div className="mb-4 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </div>
      )}

      <section className="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <label className="mb-1 block text-sm font-medium" htmlFor="case">
          القضية
        </label>
        {casesLoading ? (
          <p className="text-sm text-gray-500">جارٍ تحميل القضايا…</p>
        ) : cases.length === 0 ? (
          <p className="text-sm text-gray-500">لا توجد قضايا متاحة لك.</p>
        ) : (
          <select
            id="case"
            value={selectedCaseId}
            onChange={(e) => setSelectedCaseId(e.target.value)}
            className="w-full rounded border border-gray-300 bg-white px-3 py-2"
          >
            <option value="">— اختر قضية —</option>
            {cases.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title} — {c.client_name}
              </option>
            ))}
          </select>
        )}

        {selectedCaseId && canEdit && (
          <form onSubmit={onCreate} className="mt-4 grid gap-3 border-t border-gray-100 pt-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium" htmlFor="title">
                عنوان الموعد
              </label>
              <input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full rounded border border-gray-300 px-3 py-2"
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium" htmlFor="due">
                تاريخ الاستحقاق
              </label>
              <input
                id="due"
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="w-full rounded border border-gray-300 px-3 py-2"
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium" htmlFor="responsible">
                المحامي المسؤول
              </label>
              <select
                id="responsible"
                value={responsible}
                onChange={(e) => setResponsible(e.target.value)}
                className="w-full rounded border border-gray-300 bg-white px-3 py-2"
                required
              >
                <option value="">— اختر —</option>
                {detail?.assignments.map((a) => (
                  <option key={a.user_id} value={a.user_id}>
                    {a.full_name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium" htmlFor="basis">
                السند (اختياري)
              </label>
              <input
                id="basis"
                value={basis}
                onChange={(e) => setBasis(e.target.value)}
                className="w-full rounded border border-gray-300 px-3 py-2"
              />
            </div>
            <div className="sm:col-span-2">
              <button
                type="submit"
                disabled={creating}
                className="rounded bg-blue-700 px-5 py-2 font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
              >
                {creating ? 'جارٍ الحفظ…' : 'إضافة موعد'}
              </button>
              {formError && <span className="mr-3 text-sm text-red-700">{formError}</span>}
            </div>
          </form>
        )}
      </section>

      {selectedCaseId && (
        <section className="rounded-xl border border-gray-200 bg-white shadow-sm">
          <h2 className="border-b border-gray-100 px-5 py-3 font-semibold">مواعيد القضية</h2>
          {detailLoading ? (
            <p className="p-5 text-sm text-gray-500">جارٍ التحميل…</p>
          ) : !detail || detail.deadlines.length === 0 ? (
            <p className="p-5 text-sm text-gray-500">لا توجد مواعيد لهذه القضية.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-right text-xs text-gray-500">
                  <th className="px-5 py-2 font-medium">العنوان</th>
                  <th className="px-5 py-2 font-medium">النوع</th>
                  <th className="px-5 py-2 font-medium">الاستحقاق</th>
                  <th className="px-5 py-2 font-medium">المسؤول</th>
                  <th className="px-5 py-2 font-medium">الحالة</th>
                  <th className="px-5 py-2 font-medium">إجراءات</th>
                </tr>
              </thead>
              <tbody>
                {detail.deadlines.map((d) => {
                  const isSuggestion = d.type !== 'general' && !d.confirmed
                  return (
                    <tr key={d.id} className="border-b border-gray-50 hover:bg-gray-50">
                      <td className="px-5 py-3 font-medium">
                        {d.title}
                        {d.low_confidence_flag && (
                          <span className="mr-2 rounded bg-amber-100 px-2 py-0.5 text-xs font-bold text-red-800">
                            ⚠ مصدر منخفض الجودة
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-3 text-gray-600">{DEADLINE_TYPE_LABELS[d.type]}</td>
                      <td className="px-5 py-3 text-gray-600" dir="ltr">
                        {d.due_date}
                      </td>
                      <td className="px-5 py-3 text-gray-600">{nameOf(d.responsible_user_id)}</td>
                      <td className="px-5 py-3">
                        {isSuggestion ? (
                          <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-900">
                            مقترح — بانتظار التأكيد
                          </span>
                        ) : d.acknowledged_at ? (
                          <span className="rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-semibold text-green-800">
                            تم الإقرار
                          </span>
                        ) : (
                          <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-semibold text-gray-700">
                            نشط
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-3">
                        <div className="flex gap-2">
                          {isSuggestion && (
                            <button
                              onClick={() => onConfirm(d.id)}
                              className="rounded bg-amber-600 px-3 py-1 text-xs font-semibold text-white hover:bg-amber-700"
                            >
                              تحقّق وتأكيد
                            </button>
                          )}
                          {!isSuggestion && !d.acknowledged_at && (
                            <button
                              onClick={() => onAcknowledge(d.id)}
                              className="rounded border border-gray-300 px-3 py-1 text-xs hover:bg-gray-50"
                            >
                              إقرار بالاستلام
                            </button>
                          )}
                          {canEdit && (
                            <button
                              onClick={() => onDelete(d.id)}
                              className="rounded px-3 py-1 text-xs text-red-700 hover:bg-red-50"
                            >
                              حذف
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  )
}

export default function DeadlinesPage() {
  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <DeadlinesScreen />
      </AppShell>
    </RequireRole>
  )
}
