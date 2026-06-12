'use client'

// All-firms dashboard (T017 / US2): firms table with status, plan, trial expiry,
// usage counts, attention flags. No work-product fields anywhere. [FR-310]

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { adminGet } from '@/lib/adminApi'

interface FirmListItem {
  id: string
  name: string
  slug: string
  status: string
  plan: string | null
  trial_ends_at: string | null
  created_at: string
  attention_flags: string[]
}

const STATUS_LABEL: Record<string, string> = {
  trial: 'تجربة',
  active: 'نشط',
  past_due: 'متأخر',
  suspended: 'موقوف',
  cancelled: 'ملغى',
}

const STATUS_COLOR: Record<string, string> = {
  trial: 'bg-blue-100 text-blue-700',
  active: 'bg-green-100 text-green-700',
  past_due: 'bg-amber-100 text-amber-700',
  suspended: 'bg-red-100 text-red-700',
  cancelled: 'bg-gray-100 text-gray-500',
}

const FLAG_LABEL: Record<string, string> = {
  trial_expiring: '⏰ تجربة تنتهي قريباً',
  payment_failed: '💳 دفع متأخر',
  unprocessed_event: '📬 حدث فوترة معلّق',
}

export default function AdminDashboardPage() {
  const router = useRouter()
  const [firms, setFirms] = useState<FirmListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [planFilter, setPlanFilter] = useState('')

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (search) params.set('q', search)
      if (statusFilter) params.set('status', statusFilter)
      if (planFilter) params.set('plan', planFilter)
      const data = await adminGet<FirmListItem[]>(`/admin/firms?${params}`)
      setFirms(data)
    } catch {
      setError('فشل تحميل المكاتب')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [search, statusFilter, planFilter])

  const attention = firms.filter((f) => f.attention_flags.length > 0)

  return (
    <div dir="rtl">
      <h1 className="mb-4 text-xl font-bold">لوحة المكاتب</h1>

      {/* Attention strip */}
      {attention.length > 0 && (
        <div className="mb-4 rounded border border-amber-200 bg-amber-50 p-3">
          <p className="mb-1 text-sm font-semibold text-amber-800">تتطلب انتباهاً ({attention.length})</p>
          <div className="flex flex-wrap gap-2">
            {attention.map((f) => (
              <button
                key={f.id}
                onClick={() => router.push(`/admin/firms/${f.id}`)}
                className="rounded bg-amber-100 px-2 py-1 text-xs text-amber-900 hover:bg-amber-200"
              >
                {f.name} — {f.attention_flags.map((fl) => FLAG_LABEL[fl] ?? fl).join(', ')}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="mb-4 flex flex-wrap gap-2">
        <input
          type="text"
          placeholder="بحث بالاسم أو المعرف…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="rounded border border-gray-300 px-3 py-1 text-sm"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        >
          <option value="">الحالة: الكل</option>
          {Object.entries(STATUS_LABEL).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
        <select
          value={planFilter}
          onChange={(e) => setPlanFilter(e.target.value)}
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        >
          <option value="">الخطة: الكل</option>
          <option value="basic">Basic</option>
          <option value="pro">Pro</option>
          <option value="enterprise">Enterprise</option>
        </select>
      </div>

      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      {loading ? (
        <p className="text-sm text-gray-400">جارٍ التحميل…</p>
      ) : (
        <div className="overflow-x-auto rounded border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-gray-200 bg-gray-50 text-right">
              <tr>
                <th className="px-4 py-2 font-medium">المكتب</th>
                <th className="px-4 py-2 font-medium">المعرف</th>
                <th className="px-4 py-2 font-medium">الحالة</th>
                <th className="px-4 py-2 font-medium">الخطة</th>
                <th className="px-4 py-2 font-medium">انتهاء التجربة</th>
                <th className="px-4 py-2 font-medium">تسجيل</th>
              </tr>
            </thead>
            <tbody>
              {firms.map((f) => (
                <tr
                  key={f.id}
                  onClick={() => router.push(`/admin/firms/${f.id}`)}
                  className="cursor-pointer border-b border-gray-100 hover:bg-gray-50"
                >
                  <td className="px-4 py-2 font-medium">
                    {f.name}
                    {f.attention_flags.length > 0 && (
                      <span className="mr-1 text-amber-500">●</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-gray-500 ltr">{f.slug}</td>
                  <td className="px-4 py-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLOR[f.status] ?? 'bg-gray-100 text-gray-600'}`}>
                      {STATUS_LABEL[f.status] ?? f.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-600">{f.plan ?? '—'}</td>
                  <td className="px-4 py-2 text-gray-600">
                    {f.trial_ends_at ? new Date(f.trial_ends_at).toLocaleDateString('ar-EG') : '—'}
                  </td>
                  <td className="px-4 py-2 text-gray-500">
                    {new Date(f.created_at).toLocaleDateString('ar-EG')}
                  </td>
                </tr>
              ))}
              {firms.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-gray-400">
                    لا توجد مكاتب
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
