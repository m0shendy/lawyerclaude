'use client'

// VersionHistory — version chain list for a document (spec 002 US4, T033).
// Calls GET /documents/{id}/versions, renders newest-first.
// Shows "Checked out by [name]" badge when document is locked.

import { useEffect, useState } from 'react'
import { apiGet } from '@/lib/api'

interface DocumentVersion {
  id: string
  document_id: string
  version_number: number
  file_path: string
  file_name: string
  prev_version_id: string | null
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

interface VersionHistoryProps {
  documentId: string
  supabaseUrl: string
  storageBucket: string
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString('ar-EG', { dateStyle: 'short', timeStyle: 'short' })
}

export default function VersionHistory({ documentId, supabaseUrl, storageBucket }: VersionHistoryProps) {
  const [versions, setVersions] = useState<DocumentVersion[]>([])
  const [checkout, setCheckout] = useState<CheckoutInfo | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      apiGet<DocumentVersion[]>(`/documents/${documentId}/versions`),
      apiGet<CheckoutInfo | null>(`/documents/${documentId}/checkout`),
    ])
      .then(([vers, co]) => { setVersions(vers); setCheckout(co) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [documentId])

  if (loading) return <div className="text-xs text-gray-400">جارٍ التحميل…</div>

  return (
    <div className="space-y-2">
      {checkout && (
        <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800">
          <span>🔒</span>
          <span>
            محجوز للتعديل بواسطة <strong>{checkout.checked_out_by_name ?? 'مستخدم'}</strong>
            {' '}منذ {fmtDate(checkout.checked_out_at)}
          </span>
        </div>
      )}

      {versions.length === 0 && (
        <p className="text-xs text-gray-400">لا توجد نسخ مسجّلة — النسخة الأصلية هي v1</p>
      )}

      <ol className="space-y-1">
        {versions.map((v, i) => {
          const downloadUrl =
            `${supabaseUrl}/storage/v1/object/public/${storageBucket}/${v.file_path}`
          return (
            <li
              key={v.id}
              className={`flex items-start gap-3 rounded-lg border px-3 py-2 text-sm ${
                i === 0 ? 'border-blue-200 bg-blue-50' : 'border-gray-100 bg-white'
              }`}
            >
              <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 font-mono text-xs text-gray-600">
                v{v.version_number}
              </span>
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{v.file_name}</p>
                {v.note && <p className="text-xs text-gray-500">{v.note}</p>}
                <p className="text-xs text-gray-400">
                  {fmtDate(v.uploaded_at)}
                  {i === 0 && <span className="mr-2 text-blue-600">● الأحدث</span>}
                </p>
              </div>
              <a
                href={downloadUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="shrink-0 rounded border border-gray-300 px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-100"
              >
                تنزيل
              </a>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
