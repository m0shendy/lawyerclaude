'use client'

// Unified calendar (spec 002 US8): month/week view over hearings + appointments
// from GET /calendar (the calendar_events DB view). Event chips link to the
// underlying record list pages.

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet } from '@/lib/api'
import { ALL_ROLES, RequireRole } from '@/lib/rbac'
import type { CalendarEvent } from '@/lib/types'

type ViewMode = 'month' | 'week'
type TypeFilter = 'all' | 'hearing' | 'appointment'

const TYPE_CHIPS: Array<{ value: TypeFilter; label: string }> = [
  { value: 'all', label: 'الكل' },
  { value: 'hearing', label: 'الجلسات' },
  { value: 'appointment', label: 'المواعيد' },
]

const EVENT_COLORS: Record<CalendarEvent['event_type'], string> = {
  hearing: 'bg-violet-100 text-violet-900 border-violet-300',
  appointment: 'bg-blue-100 text-blue-900 border-blue-300',
}

const EVENT_LABELS: Record<CalendarEvent['event_type'], string> = {
  hearing: 'جلسة',
  appointment: 'موعد',
}

const WEEKDAYS = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function rangeFor(view: ViewMode, anchor: Date): { from: Date; to: Date } {
  if (view === 'week') {
    const from = new Date(anchor)
    from.setDate(anchor.getDate() - anchor.getDay()) // week starts Sunday
    const to = new Date(from)
    to.setDate(from.getDate() + 6)
    return { from, to }
  }
  const from = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
  const to = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0)
  return { from, to }
}

function CalendarScreen() {
  const [view, setView] = useState<ViewMode>('month')
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')
  const [anchor, setAnchor] = useState(() => new Date())
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<CalendarEvent | null>(null)

  const { from, to } = useMemo(() => rangeFor(view, anchor), [view, anchor])

  useEffect(() => {
    setLoading(true)
    setError(null)
    const params = new URLSearchParams({ from: ymd(from), to: ymd(to) })
    if (typeFilter !== 'all') params.set('type', typeFilter)
    apiGet<CalendarEvent[]>(`/calendar?${params}`)
      .then(setEvents)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'حدث خطأ'))
      .finally(() => setLoading(false))
  }, [from, to, typeFilter])

  const byDay = useMemo(() => {
    const acc: Record<string, CalendarEvent[]> = {}
    for (const ev of events) {
      const day = ev.starts_at.slice(0, 10)
      ;(acc[day] ??= []).push(ev)
    }
    return acc
  }, [events])

  function navigate(dir: -1 | 1) {
    const next = new Date(anchor)
    if (view === 'month') next.setMonth(anchor.getMonth() + dir)
    else next.setDate(anchor.getDate() + dir * 7)
    setAnchor(next)
    setSelected(null)
  }

  // Build the day-cell grid for the current range.
  const days: Date[] = useMemo(() => {
    const list: Date[] = []
    if (view === 'week') {
      for (let i = 0; i < 7; i++) {
        const d = new Date(from)
        d.setDate(from.getDate() + i)
        list.push(d)
      }
      return list
    }
    // month: pad to full weeks
    const start = new Date(from)
    start.setDate(from.getDate() - from.getDay())
    const end = new Date(to)
    end.setDate(to.getDate() + (6 - to.getDay()))
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      list.push(new Date(d))
    }
    return list
  }, [view, from, to])

  const title =
    view === 'month'
      ? anchor.toLocaleDateString('ar-EG', { month: 'long', year: 'numeric' })
      : `أسبوع ${from.toLocaleDateString('ar-EG')} – ${to.toLocaleDateString('ar-EG')}`

  const todayKey = ymd(new Date())

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-bold">التقويم</h1>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => navigate(1)}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
          >
            التالي ←
          </button>
          <span className="min-w-40 text-center text-sm font-semibold">{title}</span>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
          >
            → السابق
          </button>
          <button
            type="button"
            onClick={() => setAnchor(new Date())}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
          >
            اليوم
          </button>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {(['month', 'week'] as ViewMode[]).map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => setView(v)}
            className={`rounded-full px-3 py-1 text-xs ${
              view === v ? 'bg-blue-700 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {v === 'month' ? 'شهر' : 'أسبوع'}
          </button>
        ))}
        <span className="mx-2 text-gray-300">|</span>
        {TYPE_CHIPS.map((c) => (
          <button
            key={c.value}
            type="button"
            onClick={() => setTypeFilter(c.value)}
            className={`rounded-full px-3 py-1 text-xs ${
              typeFilter === c.value
                ? 'bg-blue-700 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-300 bg-red-50 px-4 py-3 text-red-800">
          {error}
        </div>
      )}

      {loading ? (
        <p className="p-8 text-center text-gray-500">جارٍ التحميل…</p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="grid grid-cols-7 border-b border-gray-200 bg-gray-50 text-center text-xs font-semibold text-gray-600">
            {WEEKDAYS.map((d) => (
              <div key={d} className="px-2 py-2">
                {d}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {days.map((d) => {
              const key = ymd(d)
              const inMonth = view === 'week' || d.getMonth() === anchor.getMonth()
              const dayEvents = byDay[key] ?? []
              return (
                <div
                  key={key}
                  className={`min-h-24 border-b border-l border-gray-100 p-1.5 ${
                    inMonth ? '' : 'bg-gray-50 opacity-60'
                  } ${key === todayKey ? 'ring-2 ring-inset ring-blue-400' : ''}`}
                >
                  <div className="mb-1 text-xs font-semibold text-gray-500">{d.getDate()}</div>
                  <div className="space-y-1">
                    {dayEvents.map((ev) => (
                      <button
                        key={`${ev.event_type}-${ev.id}`}
                        type="button"
                        onClick={() => setSelected(ev)}
                        className={`block w-full truncate rounded border px-1.5 py-0.5 text-right text-xs ${EVENT_COLORS[ev.event_type]}`}
                        title={ev.title}
                      >
                        {EVENT_LABELS[ev.event_type]} · {ev.title}
                      </button>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* تفاصيل سريعة للحدث المحدد */}
      {selected && (
        <div className="mt-4 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">
              {EVENT_LABELS[selected.event_type]} — {selected.title}
            </h2>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              ✕ إغلاق
            </button>
          </div>
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-xs text-gray-500">البداية</dt>
              <dd>{new Date(selected.starts_at).toLocaleString('ar-EG')}</dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">النهاية</dt>
              <dd>{new Date(selected.ends_at).toLocaleString('ar-EG')}</dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">الحالة</dt>
              <dd>{selected.status}</dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">السجل الكامل</dt>
              <dd>
                <Link
                  href={selected.event_type === 'hearing' ? '/hearings' : '/appointments'}
                  className="text-blue-700 hover:underline"
                >
                  فتح {EVENT_LABELS[selected.event_type]}
                </Link>
                {selected.case_id && (
                  <>
                    {' · '}
                    <Link href={`/cases/${selected.case_id}`} className="text-blue-700 hover:underline">
                      القضية
                    </Link>
                  </>
                )}
              </dd>
            </div>
          </dl>
        </div>
      )}
    </>
  )
}

export default function CalendarPage() {
  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <CalendarScreen />
      </AppShell>
    </RequireRole>
  )
}
