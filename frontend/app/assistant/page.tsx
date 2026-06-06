'use client'

/**
 * T087 — Conversational assistant screen (all roles, scoped). [C-I][C-II][C-V][C-VIII]
 *
 * In-app chat over POST /assistant/query. Retrieval is scoped server-side to the
 * caller's assigned cases [C-I]; every answer is grounded with source links [C-V]
 * and carries the assistive-tool posture [C-VIII]. "حفظ كمسودة للمراجعة" persists
 * the answer as a draft_unreviewed output so the review gate applies before any
 * official use [C-II].
 */

import { useRef, useState, type FormEvent } from 'react'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ALL_ROLES, RequireRole, useUser } from '@/lib/rbac'
import { apiPost, ApiError } from '@/lib/api'
import type { AssistantAnswer, SourceLink } from '@/lib/types'

interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  sources?: SourceLink[]
  grounded?: boolean
  savedOutputId?: string | null
}

function Sources({ sources }: { sources: SourceLink[] }) {
  if (sources.length === 0) return null
  return (
    <div className="mt-3 border-t border-gray-100 pt-2">
      <p className="mb-1 text-xs font-semibold text-gray-500">المصادر ({sources.length})</p>
      <ul className="flex flex-wrap gap-2">
        {sources.map((s, i) => (
          <li key={`${s.chunk_id}-${i}`}>
            <Link
              href={`/documents/${s.document_id}`}
              className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs text-gray-700 hover:bg-gray-200"
            >
              مصدر {i + 1}
              {s.page_ref != null ? ` — ص ${s.page_ref}` : ''}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

function AssistantScreen() {
  const { user } = useUser()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [query, setQuery] = useState('')
  const [caseId, setCaseId] = useState<string>('')
  const [saveDraft, setSaveDraft] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  const cases = user?.assigned_cases ?? []

  async function onSend(e: FormEvent) {
    e.preventDefault()
    const q = query.trim()
    if (!q || sending) return

    setError(null)
    setSending(true)
    setMessages((prev) => [...prev, { role: 'user', text: q }])
    setQuery('')

    try {
      const res = await apiPost<AssistantAnswer>('/assistant/query', {
        query: q,
        case_id: caseId || null,
        save_as_draft: saveDraft,
      })
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: res.answer,
          sources: res.sources,
          grounded: res.grounded,
          savedOutputId: res.saved_output_id,
        },
      ])
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر الحصول على إجابة')
    } finally {
      setSending(false)
      requestAnimationFrame(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }))
    }
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-12rem)] max-w-3xl flex-col">
      <div className="mb-4">
        <h1 className="text-2xl font-bold">المساعد الذكي</h1>
        <p className="mt-1 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          أداة مساعدة وليست استشارة قانونية — الإجابات مبنية على مستنداتك ضمن نطاق
          صلاحياتك، والقرار النهائي للمحامي المختص. أي مرجع قانوني للاستئناس فقط.
        </p>
      </div>

      {/* conversation */}
      <div className="flex-1 space-y-4 overflow-y-auto rounded-xl border border-gray-200 bg-gray-50 p-4">
        {messages.length === 0 && (
          <p className="p-8 text-center text-sm text-gray-400">
            اطرح سؤالاً عن قضاياك أو مستنداتك للبدء.
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={m.role === 'user' ? 'flex justify-start' : 'flex justify-end'}
          >
            <div
              className={`max-w-[85%] rounded-xl px-4 py-3 text-sm shadow-sm ${
                m.role === 'user'
                  ? 'bg-blue-700 text-white'
                  : 'border border-gray-200 bg-white text-gray-800'
              }`}
            >
              <p className="whitespace-pre-wrap leading-7">{m.text}</p>
              {m.role === 'assistant' && m.sources && <Sources sources={m.sources} />}
              {m.role === 'assistant' && m.savedOutputId && (
                <p className="mt-2 text-xs text-green-700">
                  ✓ حُفظت كمسودة بانتظار المراجعة —{' '}
                  <Link href="/ai-review" className="underline">
                    صفحة المراجعة
                  </Link>
                </p>
              )}
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {error && (
        <p className="mt-2 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
          {error}
        </p>
      )}

      {/* composer */}
      <form onSubmit={onSend} className="mt-3 space-y-2">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <select
            value={caseId}
            onChange={(e) => setCaseId(e.target.value)}
            className="rounded border border-gray-300 px-2 py-1.5"
          >
            <option value="">كل القضايا المتاحة</option>
            {cases.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-1.5 text-gray-600">
            <input
              type="checkbox"
              checked={saveDraft}
              onChange={(e) => setSaveDraft(e.target.checked)}
            />
            حفظ الإجابة كمسودة للمراجعة
          </label>
        </div>
        <div className="flex gap-2">
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void onSend(e)
              }
            }}
            rows={2}
            placeholder="اكتب سؤالك…"
            className="flex-1 resize-none rounded border border-gray-300 px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={sending || !query.trim()}
            className="rounded bg-blue-700 px-5 py-2 font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
          >
            {sending ? 'جارٍ…' : 'إرسال'}
          </button>
        </div>
      </form>
    </div>
  )
}

export default function AssistantPage() {
  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <AssistantScreen />
      </AppShell>
    </RequireRole>
  )
}
