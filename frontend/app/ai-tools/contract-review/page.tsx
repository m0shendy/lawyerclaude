'use client'

// AI Contract Review (spec 002 US2) [C-II][C-V][C-VIII][C-IX]
// POST /documents/{id}/analyze-contract  →  [analysis, clause_flag]
//
// Findings describe EXISTING document content only — no outcome prediction. [C-VIII]
// Each output born draft_unreviewed; approve/export from /ai-review. [C-II]

import { useEffect, useState } from 'react'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import AiMarkedOutput from '@/components/AiMarkedOutput'
import { ApiError, apiGet, apiPost } from '@/lib/api'
import { RequireRole } from '@/lib/rbac'
import type { AiOutput } from '@/lib/types'

interface Document {
  id: string
  file_name: string
  status: string
  case_id: string
  case_title?: string
}

interface Case {
  id: string
  title: string
}

function ContractReviewScreen() {
  const [cases, setCases] = useState<Case[]>([])
  const [docs, setDocs] = useState<Document[]>([])
  const [caseId, setCaseId] = useState('')
  const [docId, setDocId] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [outputs, setOutputs] = useState<AiOutput[]>([])

  useEffect(() => {
    apiGet<Case[]>('/cases').then(setCases).catch(() => setCases([]))
  }, [])

  useEffect(() => {
    if (!caseId) { setDocs([]); setDocId(''); return }
    apiGet<Document[]>(`/documents?case_id=${caseId}`)
      .then(d => setDocs(d.filter(doc => doc.status === 'ready' || doc.status === 'low_confidence')))
      .catch(() => setDocs([]))
  }, [caseId])

  async function runReview() {
    if (!docId) return
    setBusy(true)
    setErr(null)
    setOutputs([])
    try {
      const res = await apiPost<AiOutput[]>(`/documents/${docId}/analyze-contract`)
      setOutputs(Array.isArray(res) ? res : [res])
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'تعذّر تحليل العقد')
    } finally {
      setBusy(false)
    }
  }

  const analysisOutput = outputs.find(o => o.type === 'analysis')
  const clauseFlagOutput = outputs.find(o => o.type === 'clause_flag')

  return (
    <>
      <div className="mb-4 flex items-center gap-3">
        <Link href="/ai-tools" className="text-sm text-gray-500 hover:text-gray-700">
          ← أدوات الذكاء
        </Link>
        <span className="text-gray-300">/</span>
        <h1 className="text-xl font-bold">مراجعة العقد</h1>
      </div>
      <p className="mb-5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800">
        ⚠ المراجعة تصف المحتوى الموجود في المستند فقط — لا تتنبأ بنتائج قانونية ولا تُعدّ رأيًا قانونيًا.
        المسؤولية المهنية تقع على عاتق المحامي المراجع. {/* [C-VIII] */}
      </p>

      {/* Document selector */}
      <div className="mb-6 grid grid-cols-1 gap-3 rounded-xl border border-gray-200 bg-white p-5 shadow-sm sm:grid-cols-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-700">القضية</label>
          <select
            value={caseId}
            onChange={e => { setCaseId(e.target.value); setDocId(''); setOutputs([]) }}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="">— اختر قضية —</option>
            {cases.map(c => (
              <option key={c.id} value={c.id}>{c.title}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-700">المستند *</label>
          <select
            value={docId}
            onChange={e => { setDocId(e.target.value); setOutputs([]) }}
            disabled={!caseId}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm disabled:opacity-50"
          >
            <option value="">— اختر مستندًا —</option>
            {docs.map(d => (
              <option key={d.id} value={d.id}>
                {d.file_name}
                {d.status === 'low_confidence' ? ' ⚠' : ''}
              </option>
            ))}
          </select>
          {docs.length === 0 && caseId && (
            <p className="mt-1 text-xs text-gray-400">لا توجد مستندات جاهزة في هذه القضية</p>
          )}
        </div>
        <div className="flex items-end">
          <button
            type="button"
            onClick={runReview}
            disabled={busy || !docId}
            className="rounded-lg bg-blue-700 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
          >
            {busy ? 'جارٍ التحليل…' : '🔍 تحليل العقد'}
          </button>
        </div>
      </div>

      {err && (
        <div className="mb-4 rounded border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800">
          {err}
        </div>
      )}

      {/* Results */}
      {outputs.length > 0 && (
        <div className="space-y-5">
          <p className="text-xs text-gray-500">
            المخرجات بانتظار المراجعة — اعتمدها من{' '}
            <Link href="/ai-review" className="text-blue-700 underline">صفحة مراجعة الذكاء</Link>.
            التصدير محظور قبل الاعتماد. {/* [C-II] */}
          </p>

          {analysisOutput && (
            <section>
              <h2 className="mb-2 text-sm font-bold text-gray-700">تحليل العقد</h2>
              <AiMarkedOutput output={analysisOutput}>
                <AnalysisContent content={analysisOutput.content as Record<string, unknown>} />
              </AiMarkedOutput>
            </section>
          )}

          {clauseFlagOutput && (
            <section>
              <h2 className="mb-2 text-sm font-bold text-gray-700">البنود المُلاحَظة</h2>
              <AiMarkedOutput output={clauseFlagOutput}>
                <ClauseFlagContent content={clauseFlagOutput.content as Record<string, unknown>} />
              </AiMarkedOutput>
            </section>
          )}
        </div>
      )}
    </>
  )
}

function AnalysisContent({ content }: { content: Record<string, unknown> }) {
  const rawText = content.raw_text as string | undefined
  // Pull out any structured fields the LLM returned
  const structuredKeys = Object.keys(content).filter(
    k => k !== 'raw_text' && k !== 'context_count' && Array.isArray(content[k])
  )
  return (
    <div className="space-y-3 text-sm">
      {structuredKeys.map(key => {
        const arr = content[key] as string[]
        if (!arr?.length) return null
        return (
          <div key={key}>
            <p className="font-semibold text-gray-700 mb-1">{key.replace(/_/g, ' ')}</p>
            <ul className="list-disc list-inside space-y-1 text-gray-800">
              {arr.map((item, i) => <li key={i}>{item}</li>)}
            </ul>
          </div>
        )
      })}
      {rawText && structuredKeys.length === 0 && (
        <p className="whitespace-pre-wrap leading-relaxed text-gray-800">{rawText}</p>
      )}
    </div>
  )
}

function ClauseFlagContent({ content }: { content: Record<string, unknown> }) {
  const missing = content['البنود_الناقصة'] as string[] | undefined
  const unusual = content['البنود_غير_المعتادة'] as string[] | undefined
  const raw = content.raw_text as string | undefined

  return (
    <div className="space-y-4 text-sm">
      {missing && missing.length > 0 && (
        <div>
          <p className="mb-1 font-semibold text-red-700">📋 بنود ناقصة</p>
          <ul className="space-y-1">
            {missing.map((item, i) => (
              <li key={i} className="flex items-start gap-2 rounded border border-red-100 bg-red-50 px-3 py-1.5">
                <span className="text-red-500 shrink-0">✗</span>
                <span className="text-gray-800">{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {unusual && unusual.length > 0 && (
        <div>
          <p className="mb-1 font-semibold text-amber-700">⚠ بنود غير معتادة</p>
          <ul className="space-y-1">
            {unusual.map((item, i) => (
              <li key={i} className="flex items-start gap-2 rounded border border-amber-100 bg-amber-50 px-3 py-1.5">
                <span className="text-amber-500 shrink-0">!</span>
                <span className="text-gray-800">{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {(!missing?.length && !unusual?.length && raw) && (
        <p className="whitespace-pre-wrap leading-relaxed text-gray-800">{raw}</p>
      )}
    </div>
  )
}

export default function ContractReviewPage() {
  return (
    <RequireRole roles={['partner_manager', 'lawyer', 'paralegal']}>
      <AppShell>
        <ContractReviewScreen />
      </AppShell>
    </RequireRole>
  )
}
