'use client'

// US6 operational health (T032): worker cards, WAHA sessions, recent signups.
// Read-only — zero action buttons (FR-352).

import { useEffect, useState } from 'react'
import { adminGet } from '@/lib/adminApi'

interface WorkerHeartbeat {
  worker_name: string
  last_beat: string | null
  stale: boolean
  details: Record<string, unknown> | null
}

interface WahaSession {
  firm_slug: string
  state: string
}

interface HealthResponse {
  workers: WorkerHeartbeat[]
  waha_sessions: WahaSession[] | null
  waha_warning: string | null
  recent_signups: Array<{
    id: string
    name: string
    slug: string
    status: string
    created_at: string | null
  }>
}

const WAHA_STATE_COLOR: Record<string, string> = {
  CONNECTED: 'bg-green-100 text-green-700',
  STARTING: 'bg-blue-100 text-blue-700',
  FAILED: 'bg-red-100 text-red-700',
  STOPPED: 'bg-gray-100 text-gray-500',
}

export default function AdminHealthPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await adminGet<HealthResponse>('/admin/health')
      setHealth(data)
    } catch {
      setError('فشل تحميل بيانات الصحة التشغيلية')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div dir="rtl">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-bold">الحالة التشغيلية</h1>
        <button
          onClick={load}
          disabled={loading}
          className="rounded border border-gray-300 px-3 py-1 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-40"
        >
          {loading ? 'جارٍ التحميل…' : 'تحديث'}
        </button>
      </div>

      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      {health && (
        <>
          {/* Worker Heartbeats */}
          <section className="mb-6">
            <h2 className="mb-3 font-semibold">العمال (Workers)</h2>
            {health.workers.length === 0 ? (
              <p className="text-sm text-gray-400">لا توجد بيانات نبضات</p>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {health.workers.map((w) => (
                  <div
                    key={w.worker_name}
                    className={`rounded-xl border p-4 ${
                      w.stale ? 'border-red-200 bg-red-50' : 'border-gray-200 bg-white'
                    }`}
                  >
                    <div className="mb-1 flex items-center justify-between">
                      <p className="font-mono font-medium text-sm">{w.worker_name}</p>
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        w.stale ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'
                      }`}>
                        {w.stale ? 'متأخر' : 'نشط'}
                      </span>
                    </div>
                    <p className="text-xs text-gray-400">
                      آخر نبضة:{' '}
                      {w.last_beat
                        ? new Date(w.last_beat).toLocaleString('ar-EG')
                        : 'لم يُسجَّل'}
                    </p>
                    {w.details && (
                      <pre className="mt-2 rounded bg-gray-100 px-2 py-1 text-xs text-gray-600 overflow-auto max-h-20">
                        {JSON.stringify(w.details, null, 2)}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* WAHA Sessions */}
          <section className="mb-6">
            <h2 className="mb-3 font-semibold">جلسات WhatsApp (WAHA)</h2>
            {health.waha_warning && (
              <div className="mb-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                {health.waha_warning}
              </div>
            )}
            {health.waha_sessions === null ? (
              <p className="text-sm text-gray-400">لا توجد بيانات متاحة</p>
            ) : health.waha_sessions.length === 0 ? (
              <p className="text-sm text-gray-400">لا توجد جلسات مسجّلة</p>
            ) : (
              <div className="overflow-x-auto rounded border border-gray-200 bg-white">
                <table className="w-full text-sm">
                  <thead className="border-b border-gray-200 bg-gray-50 text-right">
                    <tr>
                      <th className="px-4 py-2 font-medium">slug المكتب</th>
                      <th className="px-4 py-2 font-medium">الحالة</th>
                    </tr>
                  </thead>
                  <tbody>
                    {health.waha_sessions.map((s) => (
                      <tr key={s.firm_slug} className="border-b border-gray-100">
                        <td className="px-4 py-2 font-mono text-xs">{s.firm_slug}</td>
                        <td className="px-4 py-2">
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            WAHA_STATE_COLOR[s.state.toUpperCase()] ?? 'bg-gray-100 text-gray-600'
                          }`}>
                            {s.state}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Recent Signups */}
          <section>
            <h2 className="mb-3 font-semibold">آخر المكاتب المسجّلة</h2>
            {health.recent_signups.length === 0 ? (
              <p className="text-sm text-gray-400">لا توجد تسجيلات</p>
            ) : (
              <div className="overflow-x-auto rounded border border-gray-200 bg-white">
                <table className="w-full text-sm">
                  <thead className="border-b border-gray-200 bg-gray-50 text-right">
                    <tr>
                      <th className="px-4 py-2 font-medium">المكتب</th>
                      <th className="px-4 py-2 font-medium">المعرّف</th>
                      <th className="px-4 py-2 font-medium">الحالة</th>
                      <th className="px-4 py-2 font-medium">تاريخ التسجيل</th>
                    </tr>
                  </thead>
                  <tbody>
                    {health.recent_signups.map((f) => (
                      <tr key={f.id} className="border-b border-gray-100">
                        <td className="px-4 py-2 font-medium">{f.name}</td>
                        <td className="px-4 py-2 font-mono text-xs text-gray-500">{f.slug}</td>
                        <td className="px-4 py-2 text-xs text-gray-500">{f.status}</td>
                        <td className="px-4 py-2 text-xs text-gray-500">
                          {f.created_at ? new Date(f.created_at).toLocaleDateString('ar-EG') : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
