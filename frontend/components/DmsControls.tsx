'use client'

// DMS controls (spec 002 US4): version history, pessimistic check-out/in,
// access level + confidentiality, and selective client sharing.
// Rendered inside the document detail page. All mutations are audit-logged
// server-side [C-III]; confidential documents cannot be shared.

import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { apiDelete, apiGet, apiPatch, apiPost, apiUpload, ApiError } from '@/lib/api'
import { useUser } from '@/lib/rbac'

interface DocumentVersion {
  id: string
  document_id: string
  version_number: number
  file_name: string
  uploaded_by: string | null
  uploaded_at: string
  note: string | null
}

interface CheckoutInfo {
  document_id: string
  checked_out_by: string
  checked_out_by_name: string | null
  checked_out_at: string
}

interface ContactOption {
  id: string
  name_ar: string
  type: string
}

const ACCESS_LABELS: Record<string, string> = {
  public: 'عام',
  team: 'فريق القضية',
  restricted: 'مقيَّد',
}

export default function DmsControls({
  documentId,
  accessLevel,
  isConfidential,
  onMetaChange,
}: {
  documentId: string
  accessLevel?: string
  isConfidential?: boolean
  onMetaChange?: () => void
}) {
  const { user } = useUser()
  const [versions, setVersions] = useState<DocumentVersion[]>([])
  const [checkout, setCheckout] = useState<CheckoutInfo | null>(null)
  const [contacts, setContacts] = useState<ContactOption[]>([])
  const [shareContact, setShareContact] = useState('')
  const [checkinFile, setCheckinFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const reload = useCallback(async () => {
    try {
      const [v, c] = await Promise.all([
        apiGet<DocumentVersion[]>(`/documents/${documentId}/versions`),
        apiGet<CheckoutInfo | null>(`/documents/${documentId}/checkout`),
      ])
      setVersions(v)
      setCheckout(c)
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'تعذّر تحميل بيانات الإصدارات')
    }
  }, [documentId])

  useEffect(() => {
    void reload()
    apiGet<ContactOption[]>('/contacts?type=client')
      .then(setContacts)
      .catch(() => setContacts([]))
  }, [reload])

  async function run(action: () => Promise<unknown>, successMsg: string) {
    setBusy(true)
    setErr(null)
    setMsg(null)
    try {
      await action()
      setMsg(successMsg)
      await reload()
      onMetaChange?.()
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'تعذّر تنفيذ الإجراء')
    } finally {
      setBusy(false)
    }
  }

  const lockedByMe = checkout != null && user != null && checkout.checked_out_by === user.id
  const lockedByOther = checkout != null && !lockedByMe

  function handleCheckin(e: FormEvent) {
    e.preventDefault()
    if (!checkinFile) return
    const form = new FormData()
    form.append('file', checkinFile)
    void run(
      () => apiUpload(`/documents/${documentId}/checkin`, form),
      'تم إيداع النسخة الجديدة وتحرير الحجز'
    ).then(() => setCheckinFile(null))
  }

  return (
    <section className="mb-4 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 font-semibold">إدارة الإصدارات والحجز</h2>

      {/* حالة الحجز */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {checkout ? (
          <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-900">
            محجوز للتعديل بواسطة {checkout.checked_out_by_name ?? 'مستخدم'} منذ{' '}
            {new Date(checkout.checked_out_at).toLocaleString('ar-EG')}
          </span>
        ) : (
          <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-800">
            متاح للحجز
          </span>
        )}

        {!checkout && (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void run(() => apiPost(`/documents/${documentId}/checkout`), 'تم حجز المستند للتعديل')
            }
            className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50"
          >
            حجز للتعديل
          </button>
        )}
        {lockedByMe && (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void run(
                () => apiDelete(`/documents/${documentId}/checkout`),
                'تم إلغاء الحجز دون إيداع نسخة'
              )
            }
            className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50"
          >
            إلغاء الحجز
          </button>
        )}
      </div>

      {/* إيداع نسخة جديدة — لصاحب الحجز فقط */}
      {lockedByMe && (
        <form onSubmit={handleCheckin} className="mb-4 flex flex-wrap items-center gap-2">
          <input
            type="file"
            onChange={(e) => setCheckinFile(e.target.files?.[0] ?? null)}
            className="text-sm"
          />
          <button
            type="submit"
            disabled={busy || !checkinFile}
            className="rounded bg-blue-700 px-4 py-1.5 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
          >
            إيداع نسخة جديدة
          </button>
        </form>
      )}
      {lockedByOther && (
        <p className="mb-4 text-xs text-gray-500">
          لا يمكن الإيداع أو التعديل حتى يُحرَّر الحجز.
        </p>
      )}

      {/* مستوى الوصول والسرية */}
      <div className="mb-4 flex flex-wrap items-center gap-3 border-t border-gray-100 pt-4">
        <label className="text-sm text-gray-600">مستوى الوصول:</label>
        <select
          value={accessLevel ?? 'team'}
          disabled={busy}
          onChange={(e) =>
            void run(
              () => apiPatch(`/documents/${documentId}/access`, { access_level: e.target.value }),
              'تم تحديث مستوى الوصول'
            )
          }
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        >
          {Object.entries(ACCESS_LABELS).map(([v, label]) => (
            <option key={v} value={v}>
              {label}
            </option>
          ))}
        </select>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={isConfidential ?? false}
            disabled={busy}
            onChange={(e) =>
              void run(
                () =>
                  apiPatch(`/documents/${documentId}/access`, {
                    is_confidential: e.target.checked,
                  }),
                e.target.checked ? 'تم وضع علامة سري' : 'تمت إزالة علامة السرية'
              )
            }
          />
          <span className="font-semibold text-red-800">مستند سري</span>
        </label>
      </div>

      {/* مشاركة مع عميل — محظورة على المستندات السرية */}
      {!isConfidential && (
        <div className="mb-4 flex flex-wrap items-center gap-2 border-t border-gray-100 pt-4">
          <label className="text-sm text-gray-600">مشاركة مع عميل:</label>
          <select
            value={shareContact}
            onChange={(e) => setShareContact(e.target.value)}
            className="rounded border border-gray-300 px-2 py-1 text-sm"
          >
            <option value="">— اختر عميلًا —</option>
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name_ar}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={busy || !shareContact}
            onClick={() =>
              void run(
                () => apiPost(`/documents/${documentId}/share`, { contact_id: shareContact }),
                'تمت مشاركة المستند مع العميل'
              )
            }
            className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50"
          >
            مشاركة
          </button>
        </div>
      )}

      {/* سلسلة الإصدارات */}
      <div className="border-t border-gray-100 pt-4">
        <h3 className="mb-2 text-sm font-semibold">سجل الإصدارات ({versions.length})</h3>
        {versions.length === 0 ? (
          <p className="text-xs text-gray-500">
            لا توجد إصدارات إضافية — النسخة الأصلية هي النسخة الحالية.
          </p>
        ) : (
          <ul className="space-y-1">
            {versions.map((v) => (
              <li
                key={v.id}
                className="flex flex-wrap items-center gap-3 rounded border border-gray-100 bg-gray-50 px-3 py-2 text-sm"
              >
                <span className="font-semibold">v{v.version_number}</span>
                <span className="text-gray-700">{v.file_name}</span>
                <span className="text-xs text-gray-500">
                  {new Date(v.uploaded_at).toLocaleString('ar-EG')}
                </span>
                {v.note && <span className="text-xs text-gray-500">({v.note})</span>}
              </li>
            ))}
          </ul>
        )}
      </div>

      {msg && <p className="mt-3 text-sm text-green-700">✓ {msg}</p>}
      {err && <p className="mt-3 text-sm text-red-700">{err}</p>}
    </section>
  )
}
