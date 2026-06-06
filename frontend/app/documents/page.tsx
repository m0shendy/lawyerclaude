'use client'

// T039 — Document upload + status screen (all roles). [C-VII]
// Upload → row born `pending`; the async pipeline advances it. We poll
// GET /documents/{id}/status every 3s while pending/processing.

import { useEffect, useRef, useState, type FormEvent } from 'react'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ALL_ROLES, RequireRole } from '@/lib/rbac'
import { apiGet, apiUpload, ApiError } from '@/lib/api'
import {
  DOCUMENT_STATUS_LABELS,
  type Case,
  type Document,
  type DocumentStatus,
} from '@/lib/types'

const STATUS_BADGE: Record<DocumentStatus, string> = {
  pending: 'bg-gray-100 text-gray-700',
  processing: 'bg-blue-100 text-blue-800',
  ready: 'bg-green-100 text-green-800',
  low_confidence: 'bg-amber-100 text-amber-900',
  failed: 'bg-red-100 text-red-800',
}

const POLLABLE: DocumentStatus[] = ['pending', 'processing']

function StatusBadge({ status }: { status: DocumentStatus }) {
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS_BADGE[status]}`}
    >
      {DOCUMENT_STATUS_LABELS[status]}
    </span>
  )
}

/** يظهر تحت صف المستند منخفض الجودة — تحذير بارز [C-VII] */
function LowConfidenceBanner() {
  return (
    <div className="flex items-center gap-2 rounded border-2 border-red-400 bg-amber-50 px-3 py-2 text-sm font-bold text-red-800">
      <span aria-hidden>⚠</span>
      جودة المسح منخفضة — راجع الأصل
    </div>
  )
}

function DocumentsScreen() {
  const [cases, setCases] = useState<Case[]>([])
  const [casesLoading, setCasesLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [selectedCaseId, setSelectedCaseId] = useState('')
  const [docs, setDocs] = useState<Document[]>([])
  const [docsLoading, setDocsLoading] = useState(false)

  const [file, setFile] = useState<File | null>(null)
  const [sourceType, setSourceType] = useState<'text_pdf' | 'scanned'>('scanned')
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // الحالة الحالية للمستندات — مرجع للاستخدام داخل مؤقّت الاستطلاع
  const docsRef = useRef<Document[]>([])
  docsRef.current = docs

  // تحميل القضايا المتاحة (مقيّدة بالدور من الخادم)
  useEffect(() => {
    let cancelled = false
    apiGet<Case[]>('/cases')
      .then((rows) => {
        if (!cancelled) setCases(rows)
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof ApiError ? err.message : 'تعذّر تحميل القضايا')
      })
      .finally(() => {
        if (!cancelled) setCasesLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // عند اختيار قضية: تحميل مستنداتها من تفاصيل القضية
  useEffect(() => {
    if (!selectedCaseId) {
      setDocs([])
      return
    }
    let cancelled = false
    setDocsLoading(true)
    setError(null)
    apiGet<{ documents: Document[] }>(`/cases/${selectedCaseId}`)
      .then((detail) => {
        if (!cancelled) setDocs(detail.documents)
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof ApiError ? err.message : 'تعذّر تحميل المستندات')
      })
      .finally(() => {
        if (!cancelled) setDocsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selectedCaseId])

  // استطلاع حالة المستندات قيد المعالجة كل 3 ثوانٍ — يُمسَح عند مغادرة الشاشة
  useEffect(() => {
    const interval = setInterval(async () => {
      const pendingDocs = docsRef.current.filter((d) => POLLABLE.includes(d.status))
      if (!pendingDocs.length) return
      for (const doc of pendingDocs) {
        try {
          const s = await apiGet<{ id: string; status: DocumentStatus; ocr_confidence: number | null }>(
            `/documents/${doc.id}/status`
          )
          if (s.status === doc.status) continue
          if (POLLABLE.includes(s.status)) {
            setDocs((prev) => prev.map((d) => (d.id === doc.id ? { ...d, status: s.status } : d)))
          } else {
            // حالة نهائية — أعد تحميل الصف كاملاً (يتضمن error_detail والثقة)
            const full = await apiGet<Document>(`/documents/${doc.id}`)
            setDocs((prev) => prev.map((d) => (d.id === doc.id ? full : d)))
          }
        } catch {
          // فشل عابر في الاستطلاع — سنحاول في الدورة التالية
        }
      }
    }, 3000)
    return () => clearInterval(interval)
  }, [])

  async function onUpload(e: FormEvent) {
    e.preventDefault()
    if (!selectedCaseId || !file) return
    setUploadError(null)
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('source_type', sourceType)
      const created = await apiUpload<Document>(`/cases/${selectedCaseId}/documents`, form)
      setDocs((prev) => [created, ...prev])
      setFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : 'فشل رفع المستند')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="mb-6 text-2xl font-bold">المستندات</h1>

      {error && (
        <div className="mb-4 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </div>
      )}

      {/* اختيار القضية */}
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
                {c.case_number ? ` (${c.case_number})` : ''}
              </option>
            ))}
          </select>
        )}

        {/* نموذج الرفع */}
        {selectedCaseId && (
          <form onSubmit={onUpload} className="mt-4 border-t border-gray-100 pt-4">
            <div className="flex flex-wrap items-end gap-4">
              <div className="min-w-64 flex-1">
                <label className="mb-1 block text-sm font-medium" htmlFor="file">
                  الملف (PDF أو صورة ممسوحة)
                </label>
                <input
                  id="file"
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf,image/jpeg,image/png,image/tiff"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm file:ml-3 file:rounded file:border-0 file:bg-blue-50 file:px-3 file:py-1 file:text-blue-700"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium" htmlFor="source_type">
                  نوع المصدر
                </label>
                <select
                  id="source_type"
                  value={sourceType}
                  onChange={(e) => setSourceType(e.target.value as 'text_pdf' | 'scanned')}
                  className="rounded border border-gray-300 bg-white px-3 py-2"
                >
                  <option value="text_pdf">PDF نصّي</option>
                  <option value="scanned">مستند ممسوح ضوئيًا</option>
                </select>
              </div>
              <button
                type="submit"
                disabled={!file || uploading}
                className="rounded bg-blue-700 px-5 py-2 font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
              >
                {uploading ? 'جارٍ الرفع…' : 'رفع المستند'}
              </button>
            </div>
            {uploadError && <p className="mt-2 text-sm text-red-700">{uploadError}</p>}
          </form>
        )}
      </section>

      {/* جدول الحالة */}
      {selectedCaseId && (
        <section className="rounded-xl border border-gray-200 bg-white shadow-sm">
          <h2 className="border-b border-gray-100 px-5 py-3 font-semibold">
            مستندات القضية وحالة المعالجة
          </h2>
          {docsLoading ? (
            <p className="p-5 text-sm text-gray-500">جارٍ تحميل المستندات…</p>
          ) : docs.length === 0 ? (
            <p className="p-5 text-sm text-gray-500">لا توجد مستندات بعد لهذه القضية.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-right text-xs text-gray-500">
                  <th className="px-5 py-2 font-medium">الملف</th>
                  <th className="px-5 py-2 font-medium">النوع</th>
                  <th className="px-5 py-2 font-medium">الحالة</th>
                  <th className="px-5 py-2 font-medium">الثقة</th>
                  <th className="px-5 py-2 font-medium">تاريخ الرفع</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((doc) => (
                  <DocRows key={doc.id} doc={doc} />
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  )
}

function DocRows({ doc }: { doc: Document }) {
  return (
    <>
      <tr className="border-b border-gray-50 hover:bg-gray-50">
        <td className="px-5 py-3">
          <Link href={`/documents/${doc.id}`} className="font-medium text-blue-700 hover:underline">
            {doc.file_name}
          </Link>
        </td>
        <td className="px-5 py-3 text-gray-600">
          {doc.source_type === 'text_pdf' ? 'PDF نصّي' : 'ممسوح ضوئيًا'}
        </td>
        <td className="px-5 py-3">
          <StatusBadge status={doc.status} />
        </td>
        <td className="px-5 py-3 text-gray-600" dir="ltr">
          {doc.ocr_confidence != null ? `${Math.round(doc.ocr_confidence * 100)}%` : '—'}
        </td>
        <td className="px-5 py-3 text-gray-600">
          {new Date(doc.uploaded_at).toLocaleDateString('ar-EG')}
        </td>
      </tr>
      {doc.status === 'low_confidence' && (
        <tr className="border-b border-gray-50">
          <td colSpan={5} className="px-5 pb-3">
            <LowConfidenceBanner />
          </td>
        </tr>
      )}
      {doc.status === 'failed' && doc.error_detail && (
        <tr className="border-b border-gray-50">
          <td colSpan={5} className="px-5 pb-3">
            <div className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
              سبب الفشل: {doc.error_detail}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

export default function DocumentsPage() {
  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <DocumentsScreen />
      </AppShell>
    </RequireRole>
  )
}
