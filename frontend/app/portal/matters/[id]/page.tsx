'use client'

// Portal matter detail — read-only (spec 002 US9, T075).
// No opposing counsel, internal notes, or audit fields shown.

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
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

export default function PortalMatterDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [matter, setMatter] = useState<PortalCase | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    const token = sessionStorage.getItem('portal_token') ?? localStorage.getItem('portal_token') ?? ''
    fetch(`${BASE}/portal/cases/${id}`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async r => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json() as Promise<PortalCase>
      })
      .then(setMatter)
      .catch(e => setErr(e.message))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return <p className="text-sm text-gray-400">جارٍ التحميل…</p>
  if (err) return <p className="text-sm text-red-600">خطأ: {err}</p>
  if (!matter) return null

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Link href="/portal/matters" className="text-sm text-gray-500 hover:text-gray-700">← القضايا</Link>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-3">
        <h2 className="text-lg font-bold">{matter.title}</h2>
        {matter.case_number && (
          <p className="text-xs text-gray-400 font-mono" dir="ltr">{matter.case_number}</p>
        )}
        <div className="grid grid-cols-2 gap-3 text-sm">
          {matter.stage && (
            <div>
              <p className="text-xs text-gray-500">المرحلة</p>
              <p className="font-medium">{STAGE_AR[matter.stage] ?? matter.stage}</p>
            </div>
          )}
          {matter.practice_area && (
            <div>
              <p className="text-xs text-gray-500">مجال الممارسة</p>
              <p className="font-medium">{matter.practice_area}</p>
            </div>
          )}
          <div>
            <p className="text-xs text-gray-500">الحالة</p>
            <p className="font-medium">{matter.status}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">تاريخ الفتح</p>
            <p className="font-medium">{new Date(matter.created_at).toLocaleDateString('ar-EG')}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
