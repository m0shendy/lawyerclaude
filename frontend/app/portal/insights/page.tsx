'use client'

// Portal AI insights — APPROVED outputs only, with AI-marked banner (spec 002 US9, T077).
// draft_unreviewed outputs are NEVER visible to portal clients [C-II][C-VI].
// Each result rendered inside AiMarkedOutput to preserve assistive-tool disclaimer [C-VIII].

import { useEffect, useState } from 'react'

const BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api'

interface PortalInsight {
  id: string
  type: string
  content: Record<string, unknown>
  approved_at: string | null
  source_links: Array<{ chunk_id: string; page_ref?: number }>
}

const TYPE_AR: Record<string, string> = {
  doc_draft: 'مسودة مستند',
  clause_flag: 'ملاحظات على البنود',
  analysis: 'تحليل',
  letter_pack: 'حزمة خطابات',
  case_timeline: 'خط زمني',
}

export default function PortalInsightsPage() {
  const [insights, setInsights] = useState<PortalInsight[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    const token = sessionStorage.getItem('portal_token') ?? localStorage.getItem('portal_token') ?? ''
    fetch(`${BASE}/portal/ai-insights`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async r => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json() as Promise<PortalInsight[]>
      })
      .then(setInsights)
      .catch(e => setErr(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-sm text-gray-400">جارٍ التحميل…</p>
  if (err) return <p className="text-sm text-red-600">خطأ: {err}</p>

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold">تقارير الذكاء الاصطناعي</h2>

      {/* Assistive-tool disclaimer always shown [C-VIII] */}
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800">
        ⚠ هذه التقارير مولّدة بالذكاء الاصطناعي وراجعها محامٍ. هي أداة مساعدة — المسؤولية المهنية تقع على عاتق المحامي.
        {/* [C-VIII] */}
      </div>

      {insights.length === 0 && (
        <div className="rounded-xl border border-gray-200 bg-white px-6 py-10 text-center">
          <p className="text-gray-400 text-sm">لا توجد تقارير معتمدة متاحة حالياً</p>
        </div>
      )}

      {insights.map(ins => {
        const text = (ins.content?.draft ?? ins.content?.raw_text ?? ins.content?.raw ?? '') as string
        return (
          <div key={ins.id} className="rounded-xl border border-blue-200 bg-blue-50 p-4 shadow-sm space-y-2">
            {/* AI-marked header [C-VI] */}
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-blue-700 px-2 py-0.5 text-xs font-semibold text-white">
                🤖 مولّد بالذكاء الاصطناعي
              </span>
              <span className="text-xs text-blue-600">{TYPE_AR[ins.type] ?? ins.type}</span>
              <span className="mr-auto text-xs text-gray-400">
                اعتُمد: {ins.approved_at ? new Date(ins.approved_at).toLocaleDateString('ar-EG') : '—'}
              </span>
            </div>
            {text ? (
              <p className="text-sm leading-relaxed text-gray-800 whitespace-pre-wrap line-clamp-8">
                {text}
              </p>
            ) : (
              <pre className="text-xs overflow-x-auto text-gray-600">
                {JSON.stringify(ins.content, null, 2).slice(0, 400)}
              </pre>
            )}
            {ins.source_links.length > 0 && (
              <p className="text-xs text-gray-400">
                {ins.source_links.length} مصدر مرجعي
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
