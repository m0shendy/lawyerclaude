'use client'

/**
 * T095 — Reference search view (all roles). [C-IX]
 *
 * Searches the firm's private reference library + the shared public-law corpus
 * for istishhad (persuasive citation). Results are framed persuasive-only:
 * explicitly NOT binding and NOT a prediction of outcome. No case content is ever
 * touched. [C-IX]
 */

import { useState, type FormEvent } from 'react'
import AppShell from '@/components/AppShell'
import { ALL_ROLES, RequireRole } from '@/lib/rbac'
import { apiPost, ApiError } from '@/lib/api'

interface ReferenceMatch {
  chunk_id: string
  document_id: string
  text: string
  page_ref: number | null
  corpus: 'private' | 'shared'
  similarity: number
  label: string
}

interface ReferenceSearchResponse {
  notice: string
  matches: ReferenceMatch[]
}

const CORPUS_LABEL: Record<string, string> = {
  private: 'مرجع المكتب',
  shared: 'القانون العام',
}

function ReferencesScreen() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<ReferenceSearchResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSearch(e: FormEvent) {
    e.preventDefault()
    const q = query.trim()
    if (!q || loading) return
    setLoading(true)
    setError(null)
    try {
      setResult(await apiPost<ReferenceSearchResponse>('/references/search', { query: q }))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر البحث')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-1 text-2xl font-bold">البحث في المراجع</h1>
      <p className="mb-4 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
        نتائج للاستئناس فقط (استشهاد) — غير مُلزِمة ولا تُعدّ تنبؤاً بنتيجة. التقدير
        القانوني النهائي للمحامي المختص.
      </p>

      <form onSubmit={onSearch} className="mb-4 flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="ابحث عن مبدأ قانوني أو سابقة…"
          className="flex-1 rounded border border-gray-300 px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="rounded bg-blue-700 px-5 py-2 font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
        >
          {loading ? 'جارٍ…' : 'بحث'}
        </button>
      </form>

      {error && (
        <p className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {result && (
        <div className="space-y-3">
          <p className="rounded bg-gray-50 p-3 text-xs text-gray-600">{result.notice}</p>
          {result.matches.length === 0 ? (
            <p className="rounded-xl border border-gray-200 bg-white p-8 text-center text-gray-500">
              لا توجد مراجع مطابقة.
            </p>
          ) : (
            result.matches.map((m) => (
              <div key={m.chunk_id} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                  <span className="rounded-full bg-blue-50 px-2 py-0.5 text-blue-800">
                    {CORPUS_LABEL[m.corpus] ?? m.corpus}
                  </span>
                  <span className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-800">
                    {m.label}
                  </span>
                  {m.page_ref != null && (
                    <span className="text-gray-400">صفحة {m.page_ref}</span>
                  )}
                  <span className="ms-auto text-gray-400" dir="ltr">
                    {Math.round(m.similarity * 100)}%
                  </span>
                </div>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-800">
                  {m.text}
                </p>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

export default function ReferencesPage() {
  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <ReferencesScreen />
      </AppShell>
    </RequireRole>
  )
}
