'use client'

// AI document tools (spec 002 US1/US12/US13): draft, letter pack, timeline.
// Every output is born draft_unreviewed and rendered through <AiMarkedOutput/>;
// approval/export happens in /ai-review (no bypass path) [C-II][C-VI].

import { useEffect, useState } from 'react'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import AiMarkedOutput from '@/components/AiMarkedOutput'
import { ApiError, apiGet, apiPost } from '@/lib/api'
import { RequireRole } from '@/lib/rbac'
import type { AiOutput, Case, TemplateSummary } from '@/lib/types'

type Tool = 'draft' | 'letter_pack' | 'timeline'

const TOOL_TABS: Array<{ key: Tool; label: string }> = [
  { key: 'draft', label: 'مسودة مستند' },
  { key: 'letter_pack', label: 'حزمة خطابات' },
  { key: 'timeline', label: 'خط زمني للقضية' },
]

const DOC_TYPES = [
  { value: 'contract', label: 'عقد' },
  { value: 'submission', label: 'مذكرة قضائية' },
  { value: 'engagement_letter', label: 'خطاب توكيل' },
  { value: 'letter', label: 'خطاب رسمي' },
]

/** يبرز عناصر [MISSING: …] باللون البرتقالي داخل النص المعروض */
function HighlightMissing({ text }: { text: string }) {
  const parts = text.split(/(\[MISSING: [^\]]+\])/g)
  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed">
      {parts.map((p, i) =>
        p.startsWith('[MISSING:') ? (
          <mark key={i} className="rounded bg-orange-200 px-1 font-semibold text-orange-900">
            {p}
          </mark>
        ) : (
          <span key={i}>{p}</span>
        )
      )}
    </p>
  )
}

interface TimelineEntry {
  date: string
  event: string
  source: string
}

function OutputView({ output }: { output: AiOutput }) {
  const content = output.content as Record<string, unknown>
  const text = (content.draft ?? content.letter ?? content.raw) as string | undefined
  const timeline = content.timeline as TimelineEntry[] | undefined

  return (
    <div className="mt-6">
      <AiMarkedOutput output={output}>
        {text && <HighlightMissing text={text} />}
        {timeline && (
          <ol className="space-y-2">
            {timeline.map((t, i) => (
              <li key={i} className="flex items-start gap-3 rounded border border-gray-100 bg-gray-50 p-2 text-sm">
                <span className="shrink-0 rounded bg-blue-100 px-2 py-0.5 font-mono text-xs text-blue-900" dir="ltr">
                  {t.date}
                </span>
                <span className="flex-1">{t.event}</span>
                <span className="shrink-0 text-xs text-gray-500">{t.source}</span>
              </li>
            ))}
          </ol>
        )}
        {!text && !timeline && (
          <pre className="overflow-x-auto text-xs">{JSON.stringify(content, null, 2)}</pre>
        )}
      </AiMarkedOutput>
      <p className="mt-2 text-xs text-gray-500">
        المخرج بانتظار المراجعة — اعتمده أو ارفضه من{' '}
        <Link href="/ai-review" className="text-blue-700 underline">
          صفحة مراجعة الذكاء
        </Link>
        . التصدير محظور قبل الاعتماد. {/* [C-II] */}
      </p>
    </div>
  )
}

function AiToolsScreen() {
  const [tool, setTool] = useState<Tool>('draft')
  const [cases, setCases] = useState<Case[]>([])
  const [templates, setTemplates] = useState<TemplateSummary[]>([])

  const [caseId, setCaseId] = useState('')
  const [docType, setDocType] = useState('contract')
  const [templateId, setTemplateId] = useState('')
  const [context, setContext] = useState('')

  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [output, setOutput] = useState<AiOutput | null>(null)

  useEffect(() => {
    apiGet<Case[]>('/cases').then(setCases).catch(() => setCases([]))
    apiGet<TemplateSummary[]>('/templates').then(setTemplates).catch(() => setTemplates([]))
  }, [])

  async function generate() {
    if (!caseId) return
    setBusy(true)
    setErr(null)
    setOutput(null)
    try {
      let res: { output: AiOutput }
      if (tool === 'draft') {
        res = await apiPost('/ai/draft-document', {
          case_id: caseId,
          doc_type: docType,
          template_id: templateId || null,
          context: context || null,
        })
      } else if (tool === 'letter_pack') {
        if (!templateId) {
          setErr('اختر نموذجًا لحزمة الخطابات')
          return
        }
        res = await apiPost('/ai/letter-pack', {
          case_id: caseId,
          template_id: templateId,
          context: context || null,
        })
      } else {
        res = await apiPost('/ai/case-timeline', { case_id: caseId })
      }
      setOutput(res.output)
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'تعذّر توليد المخرج')
    } finally {
      setBusy(false)
    }
  }

  const tabCls = (active: boolean) =>
    `px-4 py-2 text-sm font-medium border-b-2 ${
      active
        ? 'border-blue-700 text-blue-700'
        : 'border-transparent text-gray-500 hover:text-gray-700'
    }`

  return (
    <>
      <h1 className="mb-1 text-xl font-bold">أدوات الذكاء للمستندات</h1>
      <p className="mb-4 text-xs text-gray-500">
        كل المخرجات تُنشأ كمسودة بانتظار المراجعة، مستندة إلى مصادرها، ومميَّزة بصريًا.
        هذا النظام أداة مساعدة للمحامين — المسؤولية المهنية تقع على عاتق المحامي.
      </p>

      <div className="mb-4 flex gap-0 border-b border-gray-200">
        {TOOL_TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => {
              setTool(t.key)
              setOutput(null)
              setErr(null)
            }}
            className={tabCls(tool === t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-3 rounded-xl border border-gray-200 bg-white p-5 shadow-sm sm:grid-cols-3">
        <label className="text-sm">
          القضية *
          <select
            value={caseId}
            onChange={(e) => setCaseId(e.target.value)}
            className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5"
          >
            <option value="">— اختر قضية —</option>
            {cases.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </select>
        </label>

        {tool === 'draft' && (
          <label className="text-sm">
            نوع المستند
            <select
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
              className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5"
            >
              {DOC_TYPES.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
          </label>
        )}

        {(tool === 'draft' || tool === 'letter_pack') && (
          <label className="text-sm">
            النموذج {tool === 'letter_pack' ? '*' : '(اختياري)'}
            <select
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5"
            >
              <option value="">— بدون نموذج —</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name_ar}
                </option>
              ))}
            </select>
          </label>
        )}

        {tool !== 'timeline' && (
          <label className="text-sm sm:col-span-2">
            تعليمات إضافية (اختياري)
            <input
              type="text"
              value={context}
              onChange={(e) => setContext(e.target.value)}
              className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5"
            />
          </label>
        )}

        <div className="flex items-end">
          <button
            type="button"
            onClick={() => void generate()}
            disabled={busy || !caseId}
            className="rounded bg-blue-700 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
          >
            {busy ? 'جارٍ التوليد…' : 'توليد'}
          </button>
        </div>
      </div>

      {err && (
        <div className="mt-4 rounded border border-red-300 bg-red-50 px-4 py-3 text-red-800">
          {err}
        </div>
      )}

      {output && <OutputView output={output} />}
    </>
  )
}

export default function AiToolsPage() {
  return (
    <RequireRole roles={['partner_manager', 'lawyer', 'paralegal']}>
      <AppShell>
        <AiToolsScreen />
      </AppShell>
    </RequireRole>
  )
}
