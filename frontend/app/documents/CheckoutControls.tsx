'use client'

// CheckoutControls — check-out / check-in widget for DMS (spec 002 US4, T034).
// Calls POST/DELETE /documents/{id}/checkout and POST /documents/{id}/checkin.
// Shows who holds the lock if it's not the current user.

import { useRef, useState } from 'react'
import { ApiError, apiDelete, apiPost } from '@/lib/api'

interface CheckoutInfo {
  document_id: string
  checked_out_by: string
  checked_out_by_name: string | null
  checked_out_at: string
}

interface CheckoutControlsProps {
  documentId: string
  currentUserId: string
  checkout: CheckoutInfo | null
  onCheckoutChange: (info: CheckoutInfo | null) => void
  onCheckinDone?: () => void
}

export default function CheckoutControls({
  documentId, currentUserId, checkout, onCheckoutChange, onCheckinDone,
}: CheckoutControlsProps) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const isLockedByMe = checkout?.checked_out_by === currentUserId
  const isLockedByOther = checkout !== null && !isLockedByMe

  async function handleCheckout() {
    setBusy(true); setErr(null)
    try {
      const res = await apiPost<CheckoutInfo>(`/documents/${documentId}/checkout`)
      onCheckoutChange(res)
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'تعذّر حجز المستند')
    } finally { setBusy(false) }
  }

  async function handleRelease() {
    setBusy(true); setErr(null)
    try {
      await apiDelete(`/documents/${documentId}/checkout`)
      onCheckoutChange(null)
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'تعذّر إلغاء الحجز')
    } finally { setBusy(false) }
  }

  async function handleCheckin() {
    const file = fileRef.current?.files?.[0]
    if (!file) { setErr('اختر ملفًا للإيداع'); return }
    setBusy(true); setErr(null)
    const form = new FormData()
    form.append('file', file)
    try {
      const res = await fetch(`/api/documents/${documentId}/checkin`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token') ?? ''}` },
        body: form,
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body?.error?.message ?? `خطأ ${res.status}`)
      }
      onCheckoutChange(null)
      if (onCheckinDone) onCheckinDone()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'تعذّر إيداع النسخة')
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="space-y-2">
      {err && (
        <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {err}
        </div>
      )}

      {!checkout && (
        <button
          type="button"
          onClick={() => void handleCheckout()}
          disabled={busy}
          className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          {busy ? '…' : '🔒 حجز للتعديل'}
        </button>
      )}

      {isLockedByOther && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          🔒 محجوز بواسطة <strong>{checkout?.checked_out_by_name ?? 'مستخدم آخر'}</strong> — لا يمكن التعديل
        </div>
      )}

      {isLockedByMe && (
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-xs text-blue-700 font-medium">🔒 المستند محجوز لك</span>

          {/* Check-in: upload new version */}
          <label className="flex items-center gap-2 rounded-lg border border-blue-300 bg-blue-50 px-3 py-2 text-sm text-blue-700 cursor-pointer hover:bg-blue-100">
            <span>📤 إيداع نسخة جديدة</span>
            <input
              ref={fileRef}
              type="file"
              className="hidden"
              onChange={() => void handleCheckin()}
            />
          </label>

          {/* Release without new version */}
          <button
            type="button"
            onClick={() => void handleRelease()}
            disabled={busy}
            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50"
          >
            {busy ? '…' : '🔓 إلغاء الحجز'}
          </button>
        </div>
      )}
    </div>
  )
}
