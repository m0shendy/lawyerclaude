'use client'

// T037 — Users & Roles screen (manager only per ui-screens.md). [C-I][C-III]
// CRUD users, assign roles, activate/deactivate. All mutations are audited
// server-side; deactivation blocks login + the WhatsApp assistant.

import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '@/components/AppShell'
import { RequireRole } from '@/lib/rbac'
import { apiGet, apiPost, apiPatch, ApiError } from '@/lib/api'
import { ROLE_LABELS, type Role, type User } from '@/lib/types'

const ROLES: Role[] = ['partner_manager', 'lawyer', 'paralegal', 'secretary']

const inputCls = 'w-full rounded border border-gray-300 px-3 py-2'

function StatusBadge({ status }: { status: User['status'] }) {
  return status === 'active' ? (
    <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-semibold text-green-800">
      نشط
    </span>
  ) : (
    <span className="rounded-full bg-gray-200 px-2 py-0.5 text-xs font-semibold text-gray-600">
      موقوف
    </span>
  )
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('ar-EG', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    })
  } catch {
    return iso
  }
}

// ── create user form (modal) ──────────────────────────────────────────────────

function CreateUserModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (u: User) => void
}) {
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [role, setRole] = useState<Role>('lawyer')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const created = await apiPost<User>('/users', {
        full_name: fullName,
        email,
        phone: phone.trim() || null,
        role,
        password,
      })
      onCreated(created)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'حدث خطأ غير متوقع')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-lg"
      >
        <h2 className="mb-4 text-lg font-bold">إضافة مستخدم جديد</h2>

        <label className="mb-1 block text-sm font-medium" htmlFor="full_name">
          الاسم الكامل
        </label>
        <input
          id="full_name"
          type="text"
          required
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          className={`mb-3 ${inputCls}`}
        />

        <label className="mb-1 block text-sm font-medium" htmlFor="new_email">
          البريد الإلكتروني
        </label>
        <input
          id="new_email"
          type="email"
          dir="ltr"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className={`mb-3 text-left ${inputCls}`}
        />

        <label className="mb-1 block text-sm font-medium" htmlFor="new_phone">
          رقم الهاتف (اختياري)
        </label>
        <input
          id="new_phone"
          type="tel"
          dir="ltr"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          className={`mb-3 text-left ${inputCls}`}
        />

        <label className="mb-1 block text-sm font-medium" htmlFor="new_role">
          الدور
        </label>
        <select
          id="new_role"
          value={role}
          onChange={(e) => setRole(e.target.value as Role)}
          className={`mb-3 bg-white ${inputCls}`}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABELS[r]}
            </option>
          ))}
        </select>

        <label className="mb-1 block text-sm font-medium" htmlFor="new_password">
          كلمة المرور (8 أحرف على الأقل)
        </label>
        <input
          id="new_password"
          type="password"
          dir="ltr"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={`mb-4 text-left ${inputCls}`}
        />

        {error && <p className="mb-3 text-sm text-red-700">{error}</p>}

        <div className="flex gap-2">
          <button
            type="submit"
            disabled={busy}
            className="flex-1 rounded bg-blue-700 py-2 font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
          >
            {busy ? 'جارٍ الإنشاء…' : 'إنشاء المستخدم'}
          </button>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded border border-gray-300 px-4 py-2 hover:bg-gray-50 disabled:opacity-50"
          >
            إلغاء
          </button>
        </div>
      </form>
    </div>
  )
}

// ── activate/deactivate confirm dialog ────────────────────────────────────────

function StatusConfirmDialog({
  user,
  busy,
  error,
  onConfirm,
  onCancel,
}: {
  user: User
  busy: boolean
  error: string | null
  onConfirm: () => void
  onCancel: () => void
}) {
  const deactivating = user.status === 'active'
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-lg">
        <h2 className="mb-3 text-lg font-bold">
          {deactivating ? 'إلغاء تفعيل المستخدم' : 'إعادة تفعيل المستخدم'}
        </h2>
        {deactivating ? (
          <p className="mb-4 text-sm text-gray-700">
            سيتم إلغاء تفعيل حساب <span className="font-semibold">{user.full_name}</span>. لن
            يتمكن من تسجيل الدخول إلى النظام، وسيتم حظر وصوله إلى المساعد عبر واتساب. يمكنك إعادة
            التفعيل لاحقاً.
          </p>
        ) : (
          <p className="mb-4 text-sm text-gray-700">
            سيتم إعادة تفعيل حساب <span className="font-semibold">{user.full_name}</span>{' '}
            وسيستعيد القدرة على تسجيل الدخول واستخدام المساعد عبر واتساب.
          </p>
        )}

        {error && <p className="mb-3 text-sm text-red-700">{error}</p>}

        <div className="flex gap-2">
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`flex-1 rounded py-2 font-semibold text-white disabled:opacity-50 ${
              deactivating ? 'bg-red-700 hover:bg-red-800' : 'bg-green-700 hover:bg-green-800'
            }`}
          >
            {busy ? 'جارٍ التنفيذ…' : deactivating ? 'تأكيد إلغاء التفعيل' : 'تأكيد إعادة التفعيل'}
          </button>
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded border border-gray-300 px-4 py-2 hover:bg-gray-50 disabled:opacity-50"
          >
            إلغاء
          </button>
        </div>
      </div>
    </div>
  )
}

// ── page ──────────────────────────────────────────────────────────────────────

function UsersScreen() {
  const [users, setUsers] = useState<User[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [showCreate, setShowCreate] = useState(false)

  // role editing
  const [editingRoleId, setEditingRoleId] = useState<string | null>(null)
  const [roleDraft, setRoleDraft] = useState<Role>('lawyer')
  const [roleBusy, setRoleBusy] = useState(false)

  // status toggle confirm
  const [statusTarget, setStatusTarget] = useState<User | null>(null)
  const [statusBusy, setStatusBusy] = useState(false)
  const [statusError, setStatusError] = useState<string | null>(null)

  const [rowError, setRowError] = useState<string | null>(null)

  async function load() {
    setLoadError(null)
    try {
      setUsers(await apiGet<User[]>('/users'))
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : 'تعذر تحميل المستخدمين')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  function replaceUser(updated: User) {
    setUsers((prev) => prev?.map((u) => (u.id === updated.id ? updated : u)) ?? prev)
  }

  async function saveRole(user: User) {
    if (roleDraft === user.role) {
      setEditingRoleId(null)
      return
    }
    setRoleBusy(true)
    setRowError(null)
    try {
      const updated = await apiPatch<User>(`/users/${user.id}`, { role: roleDraft })
      replaceUser(updated)
      setEditingRoleId(null)
    } catch (err) {
      setRowError(err instanceof ApiError ? err.message : 'تعذر تحديث الدور')
    } finally {
      setRoleBusy(false)
    }
  }

  async function confirmStatusToggle() {
    if (!statusTarget) return
    setStatusBusy(true)
    setStatusError(null)
    try {
      const newStatus = statusTarget.status === 'active' ? 'inactive' : 'active'
      const updated = await apiPatch<User>(`/users/${statusTarget.id}`, { status: newStatus })
      replaceUser(updated)
      setStatusTarget(null)
    } catch (err) {
      setStatusError(err instanceof ApiError ? err.message : 'تعذر تغيير حالة المستخدم')
    } finally {
      setStatusBusy(false)
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">المستخدمون والأدوار</h1>
        <button
          type="button"
          onClick={() => setShowCreate(true)}
          className="rounded bg-blue-700 px-4 py-2 font-semibold text-white hover:bg-blue-800"
        >
          + إضافة مستخدم
        </button>
      </div>

      {rowError && (
        <p className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {rowError}
        </p>
      )}

      {users === null && !loadError && (
        <p className="p-8 text-center text-gray-500">جارٍ التحميل…</p>
      )}

      {loadError && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
          <p className="mb-2">{loadError}</p>
          <button
            type="button"
            onClick={() => {
              setUsers(null)
              void load()
            }}
            className="rounded border border-red-300 px-3 py-1 text-sm hover:bg-red-100"
          >
            إعادة المحاولة
          </button>
        </div>
      )}

      {users !== null && (
        <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
          <table className="w-full text-right text-sm">
            <thead className="border-b border-gray-200 bg-gray-50 text-gray-600">
              <tr>
                <th className="px-4 py-3 font-semibold">الاسم</th>
                <th className="px-4 py-3 font-semibold">البريد الإلكتروني</th>
                <th className="px-4 py-3 font-semibold">الهاتف</th>
                <th className="px-4 py-3 font-semibold">الدور</th>
                <th className="px-4 py-3 font-semibold">الحالة</th>
                <th className="px-4 py-3 font-semibold">تاريخ الإنشاء</th>
                <th className="px-4 py-3 font-semibold">إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                    لا يوجد مستخدمون بعد
                  </td>
                </tr>
              )}
              {users.map((u) => (
                <tr key={u.id} className="border-b border-gray-100 last:border-0">
                  <td className="px-4 py-3 font-medium">{u.full_name}</td>
                  <td className="px-4 py-3" dir="ltr">
                    {u.email}
                  </td>
                  <td className="px-4 py-3" dir="ltr">
                    {u.phone ?? '—'}
                  </td>
                  <td className="px-4 py-3">
                    {editingRoleId === u.id ? (
                      <span className="flex items-center gap-2">
                        <select
                          value={roleDraft}
                          onChange={(e) => setRoleDraft(e.target.value as Role)}
                          disabled={roleBusy}
                          className="rounded border border-gray-300 bg-white px-2 py-1"
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>
                              {ROLE_LABELS[r]}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          onClick={() => void saveRole(u)}
                          disabled={roleBusy}
                          className="rounded bg-blue-700 px-2 py-1 text-xs font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
                        >
                          {roleBusy ? '…' : 'حفظ'}
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingRoleId(null)}
                          disabled={roleBusy}
                          className="rounded border border-gray-300 px-2 py-1 text-xs hover:bg-gray-50 disabled:opacity-50"
                        >
                          إلغاء
                        </button>
                      </span>
                    ) : (
                      ROLE_LABELS[u.role]
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={u.status} />
                  </td>
                  <td className="px-4 py-3 text-gray-600">{formatDate(u.created_at)}</td>
                  <td className="px-4 py-3">
                    <span className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setEditingRoleId(u.id)
                          setRoleDraft(u.role)
                          setRowError(null)
                        }}
                        className="rounded border border-gray-300 px-2 py-1 text-xs hover:bg-gray-50"
                      >
                        تعديل الدور
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setStatusTarget(u)
                          setStatusError(null)
                        }}
                        className={`rounded border px-2 py-1 text-xs ${
                          u.status === 'active'
                            ? 'border-red-300 text-red-700 hover:bg-red-50'
                            : 'border-green-300 text-green-700 hover:bg-green-50'
                        }`}
                      >
                        {u.status === 'active' ? 'إلغاء التفعيل' : 'إعادة التفعيل'}
                      </button>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <CreateUserModal
          onClose={() => setShowCreate(false)}
          onCreated={(created) => {
            setUsers((prev) => (prev ? [...prev, created] : [created]))
            setShowCreate(false)
          }}
        />
      )}

      {statusTarget && (
        <StatusConfirmDialog
          user={statusTarget}
          busy={statusBusy}
          error={statusError}
          onConfirm={() => void confirmStatusToggle()}
          onCancel={() => setStatusTarget(null)}
        />
      )}
    </div>
  )
}

export default function UsersPage() {
  return (
    <RequireRole roles={['partner_manager']}>
      <AppShell>
        <UsersScreen />
      </AppShell>
    </RequireRole>
  )
}
