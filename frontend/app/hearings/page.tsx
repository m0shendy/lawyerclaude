'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet } from '@/lib/api'
import { ALL_ROLES, RequireRole } from '@/lib/rbac'
import { HEARING_STATUS_LABELS, HEARING_STATUS_COLORS, type HearingWithCase, type HearingStatus } from '@/lib/types'

const STATUS_OPTS: HearingStatus[] = ['scheduled', 'held', 'adjourned', 'cancelled']

export default function HearingsPage() {
  const [hearings, setHearings] = useState<HearingWithCase[]>([])
  const [upcoming, setUpcoming] = useState<HearingWithCase[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'upcoming' | 'all'>('upcoming')
  const [statusFilter, setStatusFilter] = useState<HearingStatus | ''>('')
  const [error, setError] = useState<string | null>(null)

  async function loadUpcoming() {
    return apiGet<HearingWithCase[]>('/hearings/upcoming?days=30')
  }

  async function loadAll() {
    const q = statusFilter ? `?status=${statusFilter}` : ''
    return apiGet<HearingWithCase[]>(`/hearings${q}`)
  }

  useEffect(() => {
    setLoading(true)
    setError(null)
    const fetch = tab === 'upcoming' ? loadUpcoming() : loadAll()
    fetch
      .then(data => {
        if (tab === 'upcoming') setUpcoming(data)
        else setHearings(data)
      })
      .catch(e => setError(e instanceof ApiError ? e.message : 'حدث خطأ'))
      .finally(() => setLoading(false))
  }, [tab, statusFilter])

  const display = tab === 'upcoming' ? upcoming : hearings

  // Group upcoming by date
  const byDate = display.reduce<Record<string, HearingWithCase[]>>((acc, h) => {
    const day = h.hearing_date.slice(0, 10)
    if (!acc[day]) acc[day] = []
    acc[day].push(h)
    return acc
  }, {})
  const sortedDates = Object.keys(byDate).sort()

  const tabCls = (active: boolean) =>
    `px-4 py-2 text-sm font-medium border-b-2 ${active ? 'border-blue-700 text-blue-700' : 'border-transparent text-gray-500 hover:text-gray-700'}`

  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <div className="mb-4 flex items-center justify-between gap-4">
          <h1 className="text-xl font-bold">الجلسات</h1>
          <Link
            href="/hearings/new"
            className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800"
          >
            + جدولة جلسة
          </Link>
        </div>

        <div className="mb-4 flex gap-0 border-b border-gray-200">
          <button onClick={() => setTab('upcoming')} className={tabCls(tab === 'upcoming')}>القادمة (30 يوم)</button>
          <button onClick={() => setTab('all')} className={tabCls(tab === 'all')}>جميع الجلسات</button>
        </div>

        {tab === 'all' && (
          <div className="mb-4 flex flex-wrap gap-2">
            <button
              onClick={() => setStatusFilter('')}
              className={`rounded-full px-3 py-1 text-xs ${statusFilter === '' ? 'bg-blue-700 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
            >
              الكل
            </button>
            {STATUS_OPTS.map(s => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`rounded-full px-3 py-1 text-xs ${statusFilter === s ? 'bg-blue-700 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
              >
                {HEARING_STATUS_LABELS[s]}
              </button>
            ))}
          </div>
        )}

        {error && <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>}

        {loading ? (
          <p className="text-sm text-gray-500">جارٍ التحميل…</p>
        ) : display.length === 0 ? (
          <p className="text-sm text-gray-500">لا توجد جلسات</p>
        ) : tab === 'upcoming' ? (
          // Calendar-style grouping by date
          <div className="space-y-6">
            {sortedDates.map(date => (
              <div key={date}>
                <h2 className="mb-2 text-sm font-semibold text-gray-500 uppercase tracking-wide">
                  {new Date(date).toLocaleDateString('ar-EG', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                </h2>
                <div className="space-y-2">
                  {byDate[date].map(h => (
                    <div key={h.id} className="flex items-center justify-between rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm hover:shadow">
                      <div className="flex items-center gap-4">
                        <span className="text-lg font-bold text-blue-700 min-w-[3.5rem] text-center">
                          {h.hearing_date.includes('T') ? h.hearing_date.slice(11, 16) : '—'}
                        </span>
                        <div>
                          <p className="font-medium text-sm">{h.court_name} {h.court_room ? `— قاعة ${h.court_room}` : ''}</p>
                          <p className="text-xs text-gray-500">{h.case_number ?? h.case_id}</p>
                          {h.notes && <p className="text-xs text-gray-400 mt-0.5">{h.notes}</p>}
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className={`rounded-full px-2 py-0.5 text-xs ${HEARING_STATUS_COLORS[h.status]}`}>
                          {HEARING_STATUS_LABELS[h.status]}
                        </span>
                        <Link href={`/hearings/${h.id}`} className="text-xs text-blue-700 hover:underline">تفاصيل</Link>
                        <Link href={`/cases/${h.case_id}`} className="text-xs text-gray-500 hover:underline">القضية</Link>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          // Flat table for "all" view
          <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-right">
                <tr>
                  <th className="px-4 py-3 font-semibold">التاريخ</th>
                  <th className="px-4 py-3 font-semibold">الوقت</th>
                  <th className="px-4 py-3 font-semibold">المحكمة</th>
                  <th className="px-4 py-3 font-semibold">القضية</th>
                  <th className="px-4 py-3 font-semibold">الحالة</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {display.map(h => (
                  <tr key={h.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">{h.hearing_date.slice(0, 10)}</td>
                    <td className="px-4 py-3">{h.hearing_date.includes('T') ? h.hearing_date.slice(11, 16) : '—'}</td>
                    <td className="px-4 py-3">{h.court_name}{h.court_room ? ` / ${h.court_room}` : ''}</td>
                    <td className="px-4 py-3 text-xs font-mono">{h.case_number ?? h.case_id.slice(0, 8)}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-0.5 text-xs ${HEARING_STATUS_COLORS[h.status]}`}>
                        {HEARING_STATUS_LABELS[h.status]}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-3">
                        <Link href={`/hearings/${h.id}`} className="text-blue-700 hover:underline text-xs">تفاصيل</Link>
                        <Link href={`/cases/${h.case_id}`} className="text-gray-500 hover:underline text-xs">القضية</Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </AppShell>
    </RequireRole>
  )
}
