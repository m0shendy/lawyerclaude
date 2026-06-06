'use client'

// T039 — Document detail: meta + grounding chunks. [C-V][C-VII]
// `?chunk=<id>` highlights the matching chunk and scrolls it into view
// (this is where AiMarkedOutput source links land).

import { Suspense, useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ALL_ROLES, RequireRole } from '@/lib/rbac'
import { apiGet, apiPost, ApiError } from '@/lib/api'
import {
  DOCUMENT_STATUS_LABELS,
  type Document,
  type DocumentStatus,
} from '@/lib/types'

// مقاطع المستند (مصادر الاستناد) — تطابق GET /documents/{id}/chunks
interface DocumentChunk {
  id: string
  document_id: string
  chunk_index: number
  chunk_text: string
  page_ref: number | null
  source_location: Record<string, unknown> | null
}

const STATUS_BADGE: Record<DocumentStatus, string> = {
  pending: 'bg-gray-100 text-gray-700',
  processing: 'bg-blue-100 text-blue-800',
  ready: 'bg-green-100 text-green-800',
  low_confidence: 'bg-amber-100 text-amber-900',
  failed: 'bg-red-100 text-red-800',
}

function MetaItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-gray-500">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium">{children}</dd>
    </div>
  )
}

// AI generation triggers — each output is born draft_unreviewed and lands in the
// review queue (/ai-review). [C-II] Enabled only once the document is processed.
function AiActions({ documentId }: { documentId: string }) {
  const [busy, setBusy] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const actions: Array<{ key: string; label: string; path: string }> = [
    { key: 'summarize', label: 'تلخيص واستخراج', path: `/documents/${documentId}/summarize` },
    { key: 'analyze', label: 'تحليل العقد', path: `/documents/${documentId}/analyze-contract` },
    { key: 'risk', label: 'إشارات المخاطر', path: `/documents/${documentId}/risk-signals` },
  ]

  async function run(key: string, path: string) {
    setBusy(key)
    setErr(null)
    setDone(null)
    try {
      await apiPost(path, {})
      setDone(key)
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'تعذّر تنفيذ الإجراء')
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="mb-4 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <h2 className="mb-1 font-semibold">إجراءات الذكاء الاصطناعي</h2>
      <p className="mb-3 text-xs text-gray-500">
        تُنشأ المخرجات كمسودة بانتظار المراجعة — راجعها واعتمدها في صفحة المراجعة.
      </p>
      <div className="flex flex-wrap gap-2">
        {actions.map((a) => (
          <button
            key={a.key}
            type="button"
            onClick={() => void run(a.key, a.path)}
            disabled={busy !== null}
            className="rounded border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-50"
          >
            {busy === a.key ? 'جارٍ…' : a.label}
          </button>
        ))}
      </div>
      {done && (
        <p className="mt-3 text-sm text-green-700">
          ✓ تم — راجع المخرجات في{' '}
          <Link href="/ai-review" className="underline">
            صفحة المراجعة
          </Link>
        </p>
      )}
      {err && <p className="mt-3 text-sm text-red-700">{err}</p>}
    </section>
  )
}

function DocumentDetailScreen() {
  const params = useParams<{ id: string }>()
  const searchParams = useSearchParams()
  const highlightedChunkId = searchParams.get('chunk')

  const [doc, setDoc] = useState<Document | null>(null)
  const [chunks, setChunks] = useState<DocumentChunk[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const highlightRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!params?.id) return
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([
      apiGet<Document>(`/documents/${params.id}`),
      apiGet<DocumentChunk[]>(`/documents/${params.id}/chunks`),
    ])
      .then(([d, c]) => {
        if (cancelled) return
        setDoc(d)
        setChunks(c)
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof ApiError ? err.message : 'تعذّر تحميل المستند')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [params?.id])

  // التمرير إلى المقطع المُشار إليه في الرابط بعد التحميل
  useEffect(() => {
    if (!loading && highlightedChunkId && highlightRef.current) {
      highlightRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [loading, highlightedChunkId, chunks])

  if (loading) {
    return <p className="p-8 text-center text-gray-500">جارٍ تحميل المستند…</p>
  }
  if (error) {
    return (
      <div className="mx-auto max-w-3xl">
        <div className="rounded border border-red-300 bg-red-50 px-4 py-3 text-red-800">
          {error}
        </div>
        <Link href="/documents" className="mt-4 inline-block text-sm text-blue-700 hover:underline">
          → العودة إلى المستندات
        </Link>
      </div>
    )
  }
  if (!doc) return null

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">{doc.file_name}</h1>
        <Link href="/documents" className="text-sm text-blue-700 hover:underline">
          → العودة إلى المستندات
        </Link>
      </div>

      {/* بيانات المستند */}
      <section className="mb-4 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <MetaItem label="الحالة">
            <span
              className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS_BADGE[doc.status]}`}
            >
              {DOCUMENT_STATUS_LABELS[doc.status]}
            </span>
          </MetaItem>
          <MetaItem label="نسبة الثقة">
            <span dir="ltr">
              {doc.ocr_confidence != null ? `${Math.round(doc.ocr_confidence * 100)}%` : '—'}
            </span>
          </MetaItem>
          <MetaItem label="نوع المصدر">
            {doc.source_type === 'text_pdf' ? 'PDF نصّي' : 'ممسوح ضوئيًا'}
          </MetaItem>
          <MetaItem label="تاريخ الرفع">
            {new Date(doc.uploaded_at).toLocaleDateString('ar-EG')}
          </MetaItem>
        </dl>

        {doc.status === 'low_confidence' && (
          <div className="mt-4 flex items-center gap-2 rounded border-2 border-red-400 bg-amber-50 px-3 py-2 text-sm font-bold text-red-800">
            <span aria-hidden>⚠</span>
            جودة المسح منخفضة — راجع الأصل
          </div>
        )}
        {doc.status === 'failed' && doc.error_detail && (
          <div className="mt-4 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
            سبب الفشل: {doc.error_detail}
          </div>
        )}
      </section>

      {/* إجراءات الذكاء الاصطناعي — متاحة بعد اكتمال المعالجة */}
      {(doc.status === 'ready' || doc.status === 'low_confidence') && (
        <AiActions documentId={doc.id} />
      )}

      {/* المقاطع (مصادر الاستناد) */}
      <section className="rounded-xl border border-gray-200 bg-white shadow-sm">
        <h2 className="border-b border-gray-100 px-5 py-3 font-semibold">
          مقاطع المستند ({chunks.length})
        </h2>
        {chunks.length === 0 ? (
          <p className="p-5 text-sm text-gray-500">
            لا توجد مقاطع بعد — تظهر المقاطع بعد اكتمال معالجة المستند.
          </p>
        ) : (
          <div className="max-h-[32rem] space-y-3 overflow-y-auto p-5">
            {chunks.map((chunk) => {
              const highlighted = chunk.id === highlightedChunkId
              return (
                <div
                  key={chunk.id}
                  ref={highlighted ? highlightRef : undefined}
                  className={`rounded-lg border p-3 ${
                    highlighted
                      ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-300'
                      : 'border-gray-200 bg-gray-50'
                  }`}
                >
                  <div className="mb-1 flex items-center gap-3 text-xs text-gray-500">
                    <span>مقطع رقم {chunk.chunk_index + 1}</span>
                    {chunk.page_ref != null && <span>صفحة {chunk.page_ref}</span>}
                    {highlighted && (
                      <span className="rounded bg-blue-600 px-1.5 py-0.5 font-semibold text-white">
                        المصدر المُشار إليه
                      </span>
                    )}
                  </div>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">{chunk.chunk_text}</p>
                </div>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}

export default function DocumentDetailPage() {
  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        {/* useSearchParams يتطلب حدود Suspense في Next.js 14 */}
        <Suspense fallback={<p className="p-8 text-center text-gray-500">جارٍ التحميل…</p>}>
          <DocumentDetailScreen />
        </Suspense>
      </AppShell>
    </RequireRole>
  )
}
