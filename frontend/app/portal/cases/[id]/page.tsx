'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

interface PortalCaseDetail {
  id: string
  case_number: string | null
  title: string
  status: string
  court_name: string | null
  description: string | null
  hearings: Array<{
    id: string
    hearing_date: string
    hearing_time: string | null
    court_name: string
    courtroom: string | null
    status: string
    notes: string | null
  }>
  tasks: Array<{
    id: string
    title: string
    status: string
    due_date: string | null
  }>
}

interface PortalDocument {
  id: string
  title: string
  file_name: string
  created_at: string
}

async function portalGet<T>(path: string, token: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? 'خطأ')
  return res.json() as Promise<T>
}

const HEARING_STATUS_AR: Record<string, string> = {
  scheduled: 'مجدوَلة', held: 'عُقدت', adjourned: 'مؤجَّلة', cancelled: 'ملغية',
}
const CASE_STATUS_AR: Record<string, string> = {
  open: 'مفتوحة', active: 'نشطة', closed: 'مغلقة', on_hold: 'معلّقة', archived: 'مؤرشفة',
}

export default function PortalCaseDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const [caseDetail, setCaseDetail] = useState<PortalCaseDetail | null>(null)
  const [documents, setDocuments] = useState<PortalDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const token = sessionStorage.getItem('portal_token')
    if (!token) { router.replace('/portal/login'); return }

    Promise.all([
      portalGet<PortalCaseDetail>(`/portal/cases/${id}`, token),
      portalGet<PortalDocument[]>(`/portal/documents?case_id=${id}`, token),
    ])
      .then(([c, d]) => { setCaseDetail(c); setDocuments(d) })
      .catch(e => {
        if (e.message?.includes('401')) { sessionStorage.removeItem('portal_token'); router.replace('/portal/login') }
        else setError(e.message ?? 'حدث خطأ')
      })
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center" dir="rtl">
      <p className="text-sm text-gray-500">جارٍ التحميل…</p>
    </div>
  )

  if (!caseDetail) return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center" dir="rtl">
      <p className="text-sm text-red-600">{error}</p>
    </div>
  )

  const upcomingHearings = caseDetail.hearings
    .filter(h => h.status === 'scheduled' && h.hearing_date >= new Date().toISOString().slice(0, 10))
    .sort((a, b) => a.hearing_date.localeCompare(b.hearing_date))

  return (
    <div className="min-h-screen bg-gray-50" dir="rtl">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white px-4 py-4">
        <div className="mx-auto max-w-3xl flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/portal/dashboard" className="text-gray-400 hover:text-gray-700">← رجوع</Link>
            <h1 className="text-base font-bold">{caseDetail.title}</h1>
          </div>
          <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
            {CASE_STATUS_AR[caseDetail.status] ?? caseDetail.status}
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-6 space-y-5">
        {error && <div className="rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>}

        {/* Case info */}
        <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <div className="grid grid-cols-2 gap-3 text-sm">
            {caseDetail.case_number && (
              <div><p className="text-xs text-gray-400">رقم القضية</p><p className="font-medium">{caseDetail.case_number}</p></div>
            )}
            {caseDetail.court_name && (
              <div><p className="text-xs text-gray-400">المحكمة</p><p className="font-medium">{caseDetail.court_name}</p></div>
            )}
          </div>
          {caseDetail.description && (
            <p className="mt-3 text-sm text-gray-600">{caseDetail.description}</p>
          )}
        </div>

        {/* Upcoming hearings */}
        <section>
          <h2 className="text-sm font-semibold mb-2">الجلسات القادمة</h2>
          {upcomingHearings.length === 0 ? (
            <p className="text-sm text-gray-500">لا توجد جلسات قادمة</p>
          ) : (
            <div className="space-y-2">
              {upcomingHearings.map(h => (
                <div key={h.id} className="flex items-center justify-between rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm">
                  <div>
                    <p className="font-medium text-sm">
                      {new Date(h.hearing_date).toLocaleDateString('ar-EG', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                      {h.hearing_time ? ` — ${h.hearing_time.slice(0, 5)}` : ''}
                    </p>
                    <p className="text-xs text-gray-400">{h.court_name}{h.courtroom ? ` · قاعة ${h.courtroom}` : ''}</p>
                    {h.notes && <p className="text-xs text-gray-400 mt-0.5">{h.notes}</p>}
                  </div>
                  <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
                    {HEARING_STATUS_AR[h.status] ?? h.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* All hearings */}
        {caseDetail.hearings.length > upcomingHearings.length && (
          <section>
            <h2 className="text-sm font-semibold mb-2">جميع الجلسات ({caseDetail.hearings.length})</h2>
            <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-right">
                  <tr>
                    <th className="px-4 py-2 font-semibold">التاريخ</th>
                    <th className="px-4 py-2 font-semibold">المحكمة</th>
                    <th className="px-4 py-2 font-semibold">الحالة</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {caseDetail.hearings.map(h => (
                    <tr key={h.id}>
                      <td className="px-4 py-2">{h.hearing_date}{h.hearing_time ? ` ${h.hearing_time.slice(0,5)}` : ''}</td>
                      <td className="px-4 py-2">{h.court_name}</td>
                      <td className="px-4 py-2">
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs">
                          {HEARING_STATUS_AR[h.status] ?? h.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* Documents */}
        <section>
          <h2 className="text-sm font-semibold mb-2">المستندات ({documents.length})</h2>
          {documents.length === 0 ? (
            <p className="text-sm text-gray-500">لا توجد مستندات مشتركة</p>
          ) : (
            <div className="rounded-xl border border-gray-200 bg-white shadow-sm divide-y divide-gray-100">
              {documents.map(doc => (
                <div key={doc.id} className="flex items-center justify-between px-4 py-3">
                  <div>
                    <p className="text-sm font-medium">{doc.title}</p>
                    <p className="text-xs text-gray-400">{doc.file_name}</p>
                  </div>
                  <span className="text-xs text-gray-400">
                    {new Date(doc.created_at).toLocaleDateString('ar-EG')}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Tasks visible to client */}
        {caseDetail.tasks.length > 0 && (
          <section>
            <h2 className="text-sm font-semibold mb-2">المهام</h2>
            <div className="rounded-xl border border-gray-200 bg-white shadow-sm divide-y divide-gray-100">
              {caseDetail.tasks.map(t => (
                <div key={t.id} className="flex items-center justify-between px-4 py-3">
                  <p className="text-sm">{t.title}</p>
                  <div className="flex items-center gap-3">
                    {t.due_date && <span className="text-xs text-gray-400">{t.due_date}</span>}
                    <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">{t.status}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  )
}
