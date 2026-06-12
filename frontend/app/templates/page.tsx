'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet, apiDelete } from '@/lib/api'
import { ALL_ROLES, RequireRole, useUser } from '@/lib/rbac'
import { TEMPLATE_CATEGORY_LABELS, type TemplateSummary, type TemplateCategory } from '@/lib/types'

const CATEGORIES: TemplateCategory[] = ['contract', 'letter', 'pleading', 'power_of_attorney', 'court_submission', 'notice', 'other']

export default function TemplatesPage() {
  const { user } = useUser()
  const [templates, setTemplates] = useState<TemplateSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [catFilter, setCatFilter] = useState<TemplateCategory | ''>('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    const q = catFilter ? `?category=${catFilter}` : ''
    apiGet<TemplateSummary[]>(`/templates${q}`)
      .then(setTemplates)
      .catch(e => setError(e instanceof ApiError ? e.message : 'حدث خطأ'))
      .finally(() => setLoading(false))
  }, [catFilter])

  async function onDelete(id: string) {
    if (!confirm('حذف هذا النموذج؟')) return
    try {
      await apiDelete(`/templates/${id}`)
      setTemplates(t => t.filter(x => x.id !== id))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    }
  }

  const isManager = user?.role === 'partner_manager'

  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold">نماذج المستندات</h1>
          {isManager && (
            <Link href="/templates/new" className="rounded bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800">
              + نموذج جديد
            </Link>
          )}
        </div>

        <div className="mb-4 flex flex-wrap gap-2">
          <button
            onClick={() => setCatFilter('')}
            className={`rounded-full px-3 py-1 text-xs ${catFilter === '' ? 'bg-blue-700 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
          >
            الكل
          </button>
          {CATEGORIES.map(c => (
            <button
              key={c}
              onClick={() => setCatFilter(c)}
              className={`rounded-full px-3 py-1 text-xs ${catFilter === c ? 'bg-blue-700 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
            >
              {TEMPLATE_CATEGORY_LABELS[c]}
            </button>
          ))}
        </div>

        {error && <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>}

        {loading ? (
          <p className="text-sm text-gray-500">جارٍ التحميل…</p>
        ) : templates.length === 0 ? (
          <p className="text-sm text-gray-500">لا توجد نماذج</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {templates.map(t => (
              <div key={t.id} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm hover:shadow">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-sm truncate">{t.name_ar}</p>
                    <span className="mt-1 inline-block rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                      {TEMPLATE_CATEGORY_LABELS[t.category]}
                    </span>
                  </div>
                  <span className="text-xs text-gray-400 shrink-0 ms-2">v{t.version}</span>
                </div>
                <div className="mt-3 flex gap-3 items-center">
                  <Link href={`/templates/${t.id}`} className="text-xs text-blue-700 hover:underline">عرض / استخدام</Link>
                  {isManager && (
                    <button onClick={() => onDelete(t.id)} className="text-xs text-red-600 hover:underline">حذف</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </AppShell>
    </RequireRole>
  )
}
