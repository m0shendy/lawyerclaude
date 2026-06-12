'use client'

// Portal matters list — read-only view for client user (spec 002 US9, T075).
// No internal notes, opposing counsel, or audit fields exposed.

import { useEffect, useState } from 'react'
import Link from 'next/link'

const BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api'

interface PortalCase {
  id: string
  title: string
  case_number: string | null
  stage: string | null
  practice_area: string | null
  status: string
  created_at: string
}

const STAGE_AR: Record<string, string> = {
  intake: 'استقبال',
  active: 'نشطة',
  litigation: 'تقاضي',
  settlement: 'تسوية',
  closed: 'مغلقة',
}

const STATUS_COLORS: Record<string, string> = {
  open: 'bg-green-100 text-green-800',
  closed: 'bg-gray-100 text-gray-600',
  lead: 'bg-blue-100 text-blue-800',
}

export default function PortalMattersPage() {
  const [cases, setCases] = useState<PortalCase[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    const token = sessionStorage.getItem('portal_token') ?? localStorage.getItem('portal_token') ?? ''
    fetch(`${BASE}/portal/cases`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async r => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json() as Promise<PortalCase[]>
      })
      .then(setCases)
      .catch(e => setErr(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-sm text-gray-400">جارٍ التحميل…</p>
  if (err) return <p className="text-sm text-red-600">خطأ: {err}</p>

  return (
    <div className="space-y-3">
      <h2 className="text-lg font-bold">قضاياي</h2>

      {cases.length === 0 && (
        <div className="rounded-xl border border-gray-200 bg-white px-6 py-10 text-center">
          <p className="text-gray-400 text-sm">لا توجد قضايا مرتبطة بحسابك</p>
        </div>
      )}

      {cases.map(c => (
        <Link
          key={c.id}
          href={`/portal/matters/${c.id}`}
          className="block rounded-xl border border-gray-200 bg-white p-4 shadow-sm hover:shadow-md"
        >
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="font-semibold text-gray-800">{c.title}</p>
              {c.case_number && <p className="text-xs text-gray-400" dir="ltr">{c.case_number}</p>}
            </div>
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[c.status] ?? 'bg-gray-100 text-gray-600'}`}>
              {c.status}
            </span>
          </div>
          {(c.stage || c.practice_area) && (
            <div className="mt-2 flex gap-2 text-xs text-gray-500">
              {c.stage && <span>{STAGE_AR[c.stage] ?? c.stage}</span>}
              {c.practice_area && <span>· {c.practice_area}</span>}
            </div>
          )}
        </Link>
      ))}
    </div>
  )
}
