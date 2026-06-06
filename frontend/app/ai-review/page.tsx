'use client'

/**
 * T060 — AI Output Review Screen. [C-II][C-V][C-VI][C-VII]
 *
 * The only screen where a lawyer/manager can:
 *  1. See all draft_unreviewed outputs in their queue.
 *  2. Read the full content with AI marking + source links.
 *  3. Click "Reviewed & Approved" → calls POST /ai-outputs/{id}/approve.
 *  4. Export (PDF/print) ONLY after approval — disabled before.
 *
 * Constitution invariants in this screen:
 *  [C-II]  Export/send disabled for draft_unreviewed; enabled only after approval.
 *  [C-V]   Every output shows per-claim source links → document chunks/pages.
 *  [C-VI]  AiMarkedOutput banner visible until approved.
 *  [C-VII] Heightened red warning when low_confidence_flag is set.
 *  [C-VIII] Persistent assistive-tool disclaimer (in root layout).
 */

import { useCallback, useEffect, useState } from 'react'
import AppShell from '@/components/AppShell'
import AiMarkedOutput from '@/components/AiMarkedOutput'
import ReviewGate from '@/components/ReviewGate'
import { ALL_ROLES, RequireRole, useUser } from '@/lib/rbac'
import { api, apiGet, apiPost, ApiError } from '@/lib/api'
import type { AiOutput, AiOutputType, ReviewState } from '@/lib/types'

// ── labels ───────────────────────────────────────────────────────────────────

const TYPE_LABELS: Record<AiOutputType, string> = {
  summary: 'ملخّص',
  extraction: 'استخراج بيانات',
  analysis: 'تحليل',
  clause_flag: 'تنبيه بند',
  risk_signal: 'إشارة مخاطرة',
}

const STATE_BADGE: Record<ReviewState, { cls: string; label: string }> = {
  draft_unreviewed: {
    cls: 'bg-violet-100 text-violet-900',
    label: 'بانتظار المراجعة',
  },
  approved: { cls: 'bg-green-100 text-green-800', label: 'معتمَد' },
}

// ── approval authority notice ─────────────────────────────────────────────────

function ApprovalNotice({ userRole }: { userRole: string }) {
  const canApprove = userRole === 'partner_manager' || userRole === 'lawyer'
  if (canApprove) return null
  return (
    <div className="mb-4 rounded border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
      دورك ({userRole === 'paralegal' ? 'مساعد قانوني' : 'سكرتير'}) لا يتيح
      الاعتماد. يتطلب اعتماد المخرجات صلاحية محامٍ مكلَّف بالقضية أو شريك/مدير.
    </div>
  )
}

// ── content renderer ─────────────────────────────────────────────────────────

function OutputContent({ content }: { content: Record<string, unknown> }) {
  const rawText = typeof content.raw_text === 'string' ? content.raw_text : null
  const sections: Array<[string, unknown]> = Object.entries(content).filter(
    ([k]) => k !== 'raw_text' && k !== 'context_count',
  )

  return (
    <div className="space-y-4 text-sm">
      {sections.length > 0 &&
        sections.map(([key, value]) => (
          <div key={key}>
            <h4 className="mb-1 font-semibold text-gray-700">{key}</h4>
            {Array.isArray(value) ? (
              <ul className="list-disc pr-5 text-gray-800">
                {(value as unknown[]).map((item, i) => (
                  <li key={i}>{String(item)}</li>
                ))}
              </ul>
            ) : (
              <p className="text-gray-800">{String(value)}</p>
            )}
          </div>
        ))}
      {rawText && sections.length === 0 && (
        <p className="whitespace-pre-wrap text-gray-800">{rawText}</p>
      )}
    </div>
  )
}

// ── output card ───────────────────────────────────────────────────────────────

interface OutputCardProps {
  output: AiOutput
  canApprove: boolean
  onApproved: (updated: AiOutput) => void
}

function OutputCard({ output, canApprove, onApproved }: OutputCardProps) {
  const [approving, setApproving] = useState(false)
  const [approveError, setApproveError] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)

  const badge = STATE_BADGE[output.review_state]

  async function handleApprove() {
    if (!canApprove) return
    setApproveError(null)
    setApproving(true)
    try {
      const updated = await apiPost<AiOutput>(`/ai-outputs/${output.id}/approve`, {
        version: 1,
      })
      onApproved(updated)
    } catch (err) {
      setApproveError(err instanceof ApiError ? err.message : 'تعذّر الاعتماد')
    } finally {
      setApproving(false)
    }
  }

  async function handleExport() {
    setExporting(true)
    try {
      // POST /ai-outputs/{id}/export — gated to approved outputs only [C-II]
      const result = await apiPost<{ content: Record<string, unknown> }>(
        `/ai-outputs/${output.id}/export`,
        {},
      )
      // Open a print-friendly window with the approved content
      const win = window.open('', '_blank')
      if (win) {
        win.document.write(
          `<html dir="rtl" lang="ar"><head><title>مخرج الذكاء الاصطناعي — معتمَد</title></head>` +
            `<body style="font-family:serif;padding:2rem;direction:rtl">` +
            `<h2>${TYPE_LABELS[output.type]} — معتمَد</h2>` +
            `<pre style="white-space:pre-wrap">${JSON.stringify(result.content, null, 2)}</pre>` +
            `</body></html>`,
        )
        win.print()
      }
    } catch (err) {
      // If not approved, the server returns 403 — that's the gate working.
      alert(err instanceof ApiError ? err.message : 'تعذّر التصدير')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
      {/* header */}
      <div className="flex flex-wrap items-center gap-3 border-b border-gray-100 px-4 py-3">
        <span className="font-semibold">{TYPE_LABELS[output.type]}</span>
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${badge.cls}`}
        >
          {badge.label}
        </span>
        {output.low_confidence_flag && (
          <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-bold text-red-800">
            ⚠ مسح منخفض الجودة
          </span>
        )}
        <span className="ms-auto text-xs text-gray-400">
          {new Date(output.created_at).toLocaleString('ar-EG')}
        </span>
      </div>

      {/* AI-marked output with source links */}
      <div className="p-4">
        <AiMarkedOutput output={output}>
          <OutputContent content={output.content as Record<string, unknown>} />
        </AiMarkedOutput>
      </div>

      {/* action buttons */}
      <div className="flex flex-wrap items-center gap-3 border-t border-gray-100 px-4 py-3">
        {/* Approve button — only for eligible roles and draft outputs */}
        {output.review_state === 'draft_unreviewed' && canApprove && (
          <button
            type="button"
            onClick={() => void handleApprove()}
            disabled={approving}
            className="rounded bg-green-700 px-5 py-2 font-semibold text-white hover:bg-green-800 disabled:opacity-50"
          >
            {approving ? 'جارٍ الاعتماد…' : '✓ تمت المراجعة والاعتماد'}
          </button>
        )}
        {approveError && (
          <p className="text-sm text-red-700">{approveError}</p>
        )}

        {/* Export — disabled via ReviewGate until approved [C-II] */}
        <ReviewGate output={output}>
          <button
            type="button"
            onClick={() => void handleExport()}
            disabled={exporting}
            className="rounded border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-50"
          >
            {exporting ? 'جارٍ التصدير…' : 'تصدير / طباعة'}
          </button>
        </ReviewGate>
      </div>
    </div>
  )
}

// ── filter bar ────────────────────────────────────────────────────────────────

type FilterState = 'all' | 'draft_unreviewed' | 'approved'

function FilterBar({
  filter,
  onChange,
}: {
  filter: FilterState
  onChange: (f: FilterState) => void
}) {
  const options: Array<{ value: FilterState; label: string }> = [
    { value: 'all', label: 'الكل' },
    { value: 'draft_unreviewed', label: 'بانتظار المراجعة' },
    { value: 'approved', label: 'معتمَد' },
  ]
  return (
    <div className="flex gap-2">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
            filter === o.value
              ? 'bg-blue-700 text-white'
              : 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

// ── page ──────────────────────────────────────────────────────────────────────

function AiReviewContent() {
  const { user } = useUser()
  const [outputs, setOutputs] = useState<AiOutput[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<FilterState>('draft_unreviewed')

  const canApprove =
    user?.role === 'partner_manager' || user?.role === 'lawyer'

  const load = useCallback(async () => {
    setError(null)
    try {
      const params = filter !== 'all' ? `?state=${filter}` : ''
      const data = await apiGet<AiOutput[]>(`/ai-outputs${params}`)
      setOutputs(data)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر تحميل المخرجات')
    }
  }, [filter])

  useEffect(() => {
    void load()
  }, [load])

  function handleApproved(updated: AiOutput) {
    setOutputs((prev) =>
      prev ? prev.map((o) => (o.id === updated.id ? updated : o)) : prev,
    )
  }

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">مراجعة مخرجات الذكاء الاصطناعي</h1>
          <p className="mt-1 text-sm text-gray-500">
            اعتمد المخرجات المدرّبة قبل استخدامها رسمياً
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
        >
          تحديث
        </button>
      </div>

      {user && <ApprovalNotice userRole={user.role} />}

      <div className="mb-4">
        <FilterBar filter={filter} onChange={setFilter} />
      </div>

      {error && (
        <p className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {outputs === null && !error && (
        <p className="p-8 text-center text-gray-500">جارٍ التحميل…</p>
      )}

      {outputs !== null && outputs.length === 0 && (
        <p className="rounded-xl border border-gray-200 bg-white p-8 text-center text-gray-500">
          لا توجد مخرجات{filter === 'draft_unreviewed' ? ' بانتظار المراجعة' : ''} حالياً
        </p>
      )}

      {outputs !== null && outputs.length > 0 && (
        <div className="space-y-4">
          {outputs.map((output) => (
            <OutputCard
              key={output.id}
              output={output}
              canApprove={canApprove}
              onApproved={handleApproved}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default function AiReviewPage() {
  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <AiReviewContent />
      </AppShell>
    </RequireRole>
  )
}
