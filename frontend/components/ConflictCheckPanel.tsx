'use client'

// Conflict-check widget (spec 002 FR-110): fires POST /contacts/conflict-check
// for an opposing-party name and shows any matches against the contacts
// registry and active matters. Every check is server-logged [C-III].

import { useState } from 'react'
import Link from 'next/link'
import { ApiError, apiPost } from '@/lib/api'

interface ConflictMatch {
  source: 'contact' | 'case_opposing_counsel'
  contact_id: string | null
  contact_type: string | null
  case_id: string | null
  case_title: string | null
  case_role: string | null
  matched_name: string
  notes: string | null
}

interface ConflictCheckResponse {
  result: 'clear' | 'conflict_found'
  conflicts: ConflictMatch[]
}

export default function ConflictCheckPanel({ partyName }: { partyName: string }) {
  const [result, setResult] = useState<ConflictCheckResponse | null>(null)
  const [checkedName, setCheckedName] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function check() {
    const name = partyName.trim()
    if (!name) return
    setBusy(true)
    setErr(null)
    try {
      setResult(await apiPost<ConflictCheckResponse>('/contacts/conflict-check', {
        party_name: name,
      }))
      setCheckedName(name)
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'تعذّر إجراء فحص التعارض')
    } finally {
      setBusy(false)
    }
  }

  const stale = result !== null && checkedName !== partyName.trim()

  return (
    <div className="rounded border border-gray-200 bg-gray-50 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void check()}
          disabled={busy || !partyName.trim()}
          className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50"
        >
          {busy ? 'جارٍ الفحص…' : 'فحص تعارض المصالح'}
        </button>
        {result && !stale && (
          result.result === 'clear' ? (
            <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-800">
              ✓ لا تعارض — «{checkedName}»
            </span>
          ) : (
            <span className="rounded-full bg-red-100 px-3 py-1 text-xs font-semibold text-red-800">
              ⚠ تعارض محتمل ({result.conflicts.length})
            </span>
          )
        )}
        {stale && (
          <span className="text-xs text-amber-700">تغيّر الاسم — أعد الفحص</span>
        )}
      </div>

      {err && <p className="mt-2 text-sm text-red-700">{err}</p>}

      {result && !stale && result.result === 'conflict_found' && (
        <ul className="mt-3 space-y-2">
          {result.conflicts.map((c, i) => (
            <li
              key={i}
              className="rounded border border-red-200 bg-white p-2 text-sm"
            >
              <span className="font-semibold">{c.matched_name}</span>
              {c.source === 'contact' ? (
                <span className="text-gray-600"> — في سجل الأطراف</span>
              ) : (
                <span className="text-gray-600"> — محامي خصم في قضية نشطة</span>
              )}
              {c.case_title && (
                <>
                  {' · '}
                  {c.case_id ? (
                    <Link href={`/cases/${c.case_id}`} className="text-blue-700 hover:underline">
                      {c.case_title}
                    </Link>
                  ) : (
                    c.case_title
                  )}
                  {c.case_role && <span className="text-xs text-gray-500"> ({c.case_role})</span>}
                </>
              )}
              {c.notes && (
                <p className="mt-1 text-xs text-gray-500">ملاحظات التعارض: {c.notes}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
