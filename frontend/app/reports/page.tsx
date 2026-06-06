'use client'

/**
 * T074 — Daily Reports screen (manager only). [C-IV]
 *
 * Read-only view of the deterministic daily digest from GET /reports/daily:
 *   • «ما حدث اليوم»  — events selected from audited data (each item is grounded
 *                       in an audit_log row server-side).
 *   • «مهام الغد»     — deadlines/tasks due tomorrow.
 *
 * The prose is an LLM phrasing-only rewording of the same items (or a
 * deterministic fallback). The items list is the authoritative record — reports
 * never go through an agent. [C-IV]
 */

import { useCallback, useEffect, useState } from 'react'
import AppShell from '@/components/AppShell'
import { MANAGER_ONLY, RequireRole } from '@/lib/rbac'
import { apiGet, ApiError } from '@/lib/api'
import type { DailyReport, ReportSection } from '@/lib/types'

function Section({ section }: { section: ReportSection }) {
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 text-lg font-bold text-gray-800">{section.heading}</h2>

      {section.items.length === 0 ? (
        <p className="text-sm text-gray-500">لا يوجد.</p>
      ) : (
        <>
          {/* Phrased prose (cosmetic) */}
          <p className="mb-4 whitespace-pre-wrap rounded bg-gray-50 p-3 text-sm leading-7 text-gray-700">
            {section.prose}
          </p>

          {/* Authoritative item list */}
          <ul className="space-y-2">
            {section.items.map((item, i) => (
              <li
                key={item.audit_id ?? item.ref_id ?? i}
                className="flex flex-wrap items-center gap-2 border-b border-gray-100 pb-2 text-sm last:border-0"
              >
                <span className="text-gray-800">{item.title}</span>
                {item.case_title && (
                  <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-800">
                    {item.case_title}
                  </span>
                )}
                {item.when && (
                  <span className="ms-auto text-xs text-gray-400">
                    {new Date(item.when).toLocaleString('ar-EG')}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

function ReportsScreen() {
  const [report, setReport] = useState<DailyReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setError(null)
    setLoading(true)
    try {
      setReport(await apiGet<DailyReport>('/reports/daily'))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر تحميل التقرير')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">التقارير اليومية</h1>
          {report && (
            <p className="mt-1 text-sm text-gray-500">
              تقرير يوم {new Date(report.report_date).toLocaleDateString('ar-EG')}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
        >
          تحديث
        </button>
      </div>

      {error && (
        <p className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {loading && !error && (
        <p className="p-8 text-center text-gray-500">جارٍ التحميل…</p>
      )}

      {report && !loading && (
        <div className="space-y-6">
          <Section section={report.what_happened} />
          <Section section={report.tomorrow} />
        </div>
      )}
    </div>
  )
}

export default function ReportsPage() {
  return (
    <RequireRole roles={MANAGER_ONLY}>
      <AppShell>
        <ReportsScreen />
      </AppShell>
    </RequireRole>
  )
}
