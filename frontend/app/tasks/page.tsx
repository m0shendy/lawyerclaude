'use client'

// T069 — Tasks screen (manager, lawyer, paralegal). [C-III]
// CRUD tasks with assignee + due date. Reminders for tasks with a due date are
// fired by the deterministic scheduler, never from this screen. [C-IV]

import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '@/components/AppShell'
import { RequireRole, useUser } from '@/lib/rbac'
import { apiGet, apiPost, apiPatch, apiDelete, ApiError } from '@/lib/api'
import {
  PRIORITY_COLORS,
  PRIORITY_LABELS,
  TASK_STATUS_LABELS,
  type Case,
  type Priority,
  type Role,
  type TaskItem,
  type TaskStatus,
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
  tasks: TaskItem[]
  assignments: Assignment[]
}

const TASK_ROLES: Role[] = ['partner_manager', 'lawyer', 'paralegal']
const STATUSES: TaskStatus[] = ['open', 'in_progress', 'done', 'cancelled']
const PRIORITIES: Priority[] = ['high', 'medium', 'low']

function TasksScreen() {
  const { user } = useUser()

  const [cases, setCases] = useState<Case[]>([])
  const [casesLoading, setCasesLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [selectedCaseId, setSelectedCaseId] = useState('')
  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [description, setDescription] = useState('')
  const [dueDate, setDueDate] = useState('')
  const [assignee, setAssignee] = useState('')
  const [priority, setPriority] = useState<Priority>('medium')
  const [priorityFilter, setPriorityFilter] = useState<Priority | ''>('')
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
      setDetail(await apiGet<CaseDetail>(`/cases/${caseId}`))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر تحميل المهام')
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    loadDetail(selectedCaseId)
    setAssignee('')
    setFormError(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCaseId])

  async function onCreate(e: FormEvent) {
    e.preventDefault()
    if (!selectedCaseId || !description || !assignee) return
    setFormError(null)
    setCreating(true)
    try {
      await apiPost<TaskItem>(`/cases/${selectedCaseId}/tasks`, {
        description,
        assigned_to: assignee,
        due_date: dueDate || null,
        priority,
      })
      setDescription('')
      setDueDate('')
      await loadDetail(selectedCaseId)
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'تعذّر إنشاء المهمة')
    } finally {
      setCreating(false)
    }
  }

  async function onStatusChange(id: string, status: TaskStatus) {
    try {
      await apiPatch(`/tasks/${id}`, { status })
      await loadDetail(selectedCaseId)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر تحديث الحالة')
    }
  }

  async function onDelete(id: string) {
    if (!confirm('حذف هذه المهمة؟')) return
    try {
      await apiDelete(`/tasks/${id}`)
      await loadDetail(selectedCaseId)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر حذف المهمة')
    }
  }

  const nameOf = (userId: string) =>
    detail?.assignments.find((a) => a.user_id === userId)?.full_name ?? userId.slice(0, 8)

  const canModify = (t: TaskItem) =>
    !!user && (user.role === 'partner_manager' || user.id === t.assigned_to)

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="mb-6 text-2xl font-bold">المهام</h1>

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

        {selectedCaseId && (
          <form onSubmit={onCreate} className="mt-4 grid gap-3 border-t border-gray-100 pt-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="mb-1 block text-sm font-medium" htmlFor="desc">
                وصف المهمة
              </label>
              <input
                id="desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full rounded border border-gray-300 px-3 py-2"
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium" htmlFor="assignee">
                المُكلَّف
              </label>
              <select
                id="assignee"
                value={assignee}
                onChange={(e) => setAssignee(e.target.value)}
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
              <label className="mb-1 block text-sm font-medium" htmlFor="due">
                تاريخ الاستحقاق (اختياري)
              </label>
              <input
                id="due"
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="w-full rounded border border-gray-300 px-3 py-2"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium" htmlFor="priority">
                الأولوية
              </label>
              <select
                id="priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value as Priority)}
                className="w-full rounded border border-gray-300 bg-white px-3 py-2"
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {PRIORITY_LABELS[p]}
                  </option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-2">
              <button
                type="submit"
                disabled={creating}
                className="rounded bg-blue-700 px-5 py-2 font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
              >
                {creating ? 'جارٍ الحفظ…' : 'إضافة مهمة'}
              </button>
              {formError && <span className="mr-3 text-sm text-red-700">{formError}</span>}
            </div>
          </form>
        )}
      </section>

      {selectedCaseId && (
        <section className="rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 px-5 py-3">
            <h2 className="font-semibold">مهام القضية</h2>
            <div className="flex gap-1.5">
              <button
                type="button"
                onClick={() => setPriorityFilter('')}
                className={`rounded-full px-3 py-1 text-xs ${
                  priorityFilter === ''
                    ? 'bg-blue-700 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                كل الأولويات
              </button>
              {PRIORITIES.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPriorityFilter(p)}
                  className={`rounded-full px-3 py-1 text-xs ${
                    priorityFilter === p
                      ? 'bg-blue-700 text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  {PRIORITY_LABELS[p]}
                </button>
              ))}
            </div>
          </div>
          {detailLoading ? (
            <p className="p-5 text-sm text-gray-500">جارٍ التحميل…</p>
          ) : !detail || detail.tasks.length === 0 ? (
            <p className="p-5 text-sm text-gray-500">لا توجد مهام لهذه القضية.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-right text-xs text-gray-500">
                  <th className="px-5 py-2 font-medium">الوصف</th>
                  <th className="px-5 py-2 font-medium">الأولوية</th>
                  <th className="px-5 py-2 font-medium">المُكلَّف</th>
                  <th className="px-5 py-2 font-medium">الاستحقاق</th>
                  <th className="px-5 py-2 font-medium">الحالة</th>
                  <th className="px-5 py-2 font-medium">إجراءات</th>
                </tr>
              </thead>
              <tbody>
                {detail.tasks
                  .filter((t) => !priorityFilter || t.priority === priorityFilter)
                  .map((t) => (
                  <tr key={t.id} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="px-5 py-3 font-medium">{t.description}</td>
                    <td className="px-5 py-3">
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${PRIORITY_COLORS[t.priority ?? 'medium']}`}
                      >
                        {PRIORITY_LABELS[t.priority ?? 'medium']}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-gray-600">{nameOf(t.assigned_to)}</td>
                    <td className="px-5 py-3 text-gray-600" dir="ltr">
                      {t.due_date ?? '—'}
                    </td>
                    <td className="px-5 py-3">
                      {canModify(t) ? (
                        <select
                          value={t.status}
                          onChange={(e) => onStatusChange(t.id, e.target.value as TaskStatus)}
                          className="rounded border border-gray-300 bg-white px-2 py-1 text-xs"
                        >
                          {STATUSES.map((s) => (
                            <option key={s} value={s}>
                              {TASK_STATUS_LABELS[s]}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className="text-gray-600">{TASK_STATUS_LABELS[t.status]}</span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      {canModify(t) && (
                        <button
                          onClick={() => onDelete(t.id)}
                          className="rounded px-3 py-1 text-xs text-red-700 hover:bg-red-50"
                        >
                          حذف
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  )
}

export default function TasksPage() {
  return (
    <RequireRole roles={TASK_ROLES}>
      <AppShell>
        <TasksScreen />
      </AppShell>
    </RequireRole>
  )
}
