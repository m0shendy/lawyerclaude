'use client'

// AI Knowledge Search (spec 002 US11) [C-IX]
// GET /ai/knowledge-search?q=&corpus=all|private|shared
//
// Read-only — no ai_outputs row created.
// Results from the shared Egyptian-law corpus display:
//   "مرجع استشهادي — غير ملزم" (persuasive reference — not binding) [C-IX]

import { useState, type FormEvent } from 'react'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet } from '@/lib/api'
import { RequireRole } from '@/lib/rbac'

type CorpusFilter = 'all' | 'private' | 'shared'

interface KnowledgeResult {
  chunk_id: string
  document_id: string
  chunk_text: string
  page_ref: number | null
  similarity: number
  corpus: string
  frame: string | null
  type: string | null
}

const CORPUS_OPTS: Array<{ value: CorpusFilter; label: string }> = [
  { value: 'all', label: 'الكل' },
  { value: 'private', label: 'قاعدة المكتب' },
  { value: 'shared', label: 'القانون المصري' },
]

function SimilarityBar({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color = pct >= 80 ? 'bg-green-500' : pct >= 60 ? 'bg-blue-500' : 'bg-gray-400'
  return (
    <div className="flex items-center gap-2 text-xs">
      <div className="w-20 h-1.5 rounded-full bg-gray-200 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-gray-500" dir="ltr">{pct}%</span>
    </div>
  )
}

function KnowledgeSearchScreen() {
  const [q, setQ] = useState('')
  const [corpus, setCorpus] = useState<CorpusFilter>('all')
  const [results, setResults] = useState<KnowledgeResult[]>([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function search(e: FormEvent) {
    e.preventDefault()
    if (q.trim().length < 3) return
    setLoading(true)
    setErr(null)
    setResults([])
    setSearched(false)
    try {
      const params = new URLSearchParams({ q: q.trim(), corpus })
      const data = await apiGet<KnowledgeResult[]>(`/ai/knowledge-search?${params}`)
      setResults(data)
      setSearched(true)
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'تعذّر البحث')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <div className="mb-4 flex items-center gap-3">
        <Link href="/ai-tools" className="text-sm text-gray-500 hover:text-gray-700">
          ← أدوات الذكاء
        </Link>
        <span className="text-gray-300">/</span>
        <h1 className="text-xl font-bold">البحث في قاعدة المعرفة</h1>
      </div>
      <p className="mb-5 text-xs text-gray-500">
        بحث دلالي في مستندات المكتب والقانون المصري. نتائج القانون المصري هي مراجع استشهادية غير ملزمة. {/* [C-IX] */}
      </p>

      {/* Search form */}
      <form onSubmit={search} className="mb-6 flex flex-wrap items-end gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="flex-1 min-w-[200px]">
          <label className="mb-1 block text-xs font-medium text-gray-700">سؤال أو موضوع</label>
          <input
            type="text"
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="مثال: شروط فسخ العقد، مدة التقادم…"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            dir="rtl"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-700">النطاق</label>
          <select
            value={corpus}
            onChange={e => setCorpus(e.target.value as CorpusFilter)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            {CORPUS_OPTS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          disabled={loading || q.trim().length < 3}
          className="rounded-lg bg-blue-700 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
        >
          {loading ? 'جارٍ البحث…' : 'بحث'}
        </button>
      </form>

      {err && (
        <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{err}</div>
      )}

      {/* Results */}
      {searched && results.length === 0 && (
        <div className="rounded-xl border border-gray-200 bg-white px-6 py-10 text-center shadow-sm">
          <p className="text-gray-500 text-sm">لا توجد نتائج مطابقة — جرّب صياغة مختلفة أو وسّع النطاق</p>
        </div>
      )}

      {results.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs text-gray-500">{results.length} نتيجة</p>
          {results.map((r, i) => (
            <div
              key={r.chunk_id}
              className={`rounded-xl border p-4 shadow-sm ${
                r.corpus === 'shared'
                  ? 'border-amber-200 bg-amber-50'
                  : 'border-gray-200 bg-white'
              }`}
            >
              {/* Header */}
              <div className="mb-2 flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-bold text-gray-500">#{i + 1}</span>
                  {r.corpus === 'shared' ? (
                    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
                      🏛 مرجع استشهادي — غير ملزم {/* [C-IX] */}
                    </span>
                  ) : (
                    <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
                      📂 قاعدة المكتب
                    </span>
                  )}
                  {r.page_ref !== null && (
                    <span className="text-xs text-gray-400">صفحة {r.page_ref}</span>
                  )}
                </div>
                <SimilarityBar score={r.similarity} />
              </div>

              {/* Chunk text */}
              <p className="text-sm leading-relaxed text-gray-800 whitespace-pre-wrap line-clamp-6">
                {r.chunk_text}
              </p>

              {r.corpus === 'shared' && (
                <p className="mt-2 text-xs text-amber-700">
                  ⚠ هذا النص من القانون المصري العام — مرجع استشهادي للمحامي، غير ملزم وغير معتمد تلقائيًا.
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  )
}

export default function KnowledgeSearchPage() {
  return (
    <RequireRole roles={['partner_manager', 'lawyer', 'paralegal']}>
      <AppShell>
        <KnowledgeSearchScreen />
      </AppShell>
    </RequireRole>
  )
}
