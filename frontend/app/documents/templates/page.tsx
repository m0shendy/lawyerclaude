'use client'

// Document templates library (spec 002 US4, T035).
// Lists all firm templates; clicking opens editor.
// "Generate Draft" calls POST /templates/{id}/generate → ai_outputs [C-II].

import { useEffect, useState } from 'react'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ApiError, apiDelete, apiGet, apiPost } from '@/lib/api'
import { RequireRole } from '@/lib/rbac'

interface Template {
  id: string
  name: string
  name_ar: string
  category: string | null
  content_template: string
  variables_schema: Record<string, unknown>[]
  created_by: string | null
  created_at: string
}

const CATEGORIES: Record<string, string> = {
  contract: 'عقد',
  submission: 'مذكرة قضائية',
  engagement_letter: 'خطاب توكيل',
  letter: 'خطاب رسمي',
  other: 'أخرى',
}

function TemplatesScreen() {
  const [templates, setTemplates] = useState<Template[]>([])
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState<string | null>(null)

  useEffect(() => {
    apiGet<Template[]>('/templates')
      .then(setTemplates)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const filtered = filter
    ? templates.filter(t => t.category === filter)
    : templates

  async function deleteTemplate(id: string) {
    if (!confirm('حذف النموذج؟ لا يمكن التراجع عن هذا الإجراء.')) return
    setDeleting(id)
    try {
      await apiDelete(`/templates/${id}`)
      setTemplates(prev => prev.filter(t => t.id !== id))
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'تعذّر الحذف')
    } finally {
      setDeleting(null)
    }
  }

  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-4">
        <h1 className="text-xl font-bold">مكتبة النماذج</h1>
        <Link
          href="/documents/templates/new"
          className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800"
        >
          + نموذج جديد
        </Link>
      </div>

      {/* Category filter */}
      <div className="mb-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setFilter('')}
          className={`rounded-full px-3 py-1 text-xs font-medium border ${!filter ? 'bg-blue-700 text-white border-blue-700' : 'border-gray-300 text-gray-600 hover:bg-gray-50'}`}
        >
          الكل
        </button>
        {Object.entries(CATEGORIES).map(([k, v]) => (
          <button
            key={k}
            type="button"
            onClick={() => setFilter(k)}
            className={`rounded-full px-3 py-1 text-xs font-medium border ${filter === k ? 'bg-blue-700 text-white border-blue-700' : 'border-gray-300 text-gray-600 hover:bg-gray-50'}`}
          >
            {v}
          </button>
        ))}
      </div>

      {loading && <p className="text-gray-400 text-sm">جارٍ التحميل…</p>}

      {!loading && filtered.length === 0 && (
        <div className="rounded-xl border border-gray-200 bg-white px-6 py-10 text-center shadow-sm">
          <p className="text-gray-500 text-sm">لا توجد نماذج — أنشئ نموذجًا جديدًا للبدء</p>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map(t => (
          <div key={t.id} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm flex flex-col gap-2">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-semibold text-gray-800">{t.name_ar}</p>
                <p className="text-xs text-gray-400">{t.name}</p>
              </div>
              {t.category && (
                <span className="shrink-0 rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
                  {CATEGORIES[t.category] ?? t.category}
                </span>
              )}
            </div>
            <p className="text-xs text-gray-500 line-clamp-2">
              {t.content_template.slice(0, 120)}…
            </p>
            <p className="text-xs text-gray-400">
              {t.variables_schema.length} متغيرات
            </p>
            <div className="mt-auto flex items-center gap-2 pt-2 border-t border-gray-100">
              <Link
                href={`/documents/templates/${t.id}`}
                className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-center text-xs font-medium text-gray-700 hover:bg-gray-50"
              >
                تعديل
              </Link>
              <button
                type="button"
                disabled={deleting === t.id}
                onClick={() => void deleteTemplate(t.id)}
                className="rounded-lg border border-red-200 px-3 py-1.5 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50"
              >
                {deleting === t.id ? '…' : 'حذف'}
              </button>
            </div>
          </div>
        ))}
      </div>
    </>
  )
}

export default function TemplatesPage() {
  return (
    <RequireRole roles={['partner_manager', 'lawyer', 'paralegal']}>
      <AppShell>
        <TemplatesScreen />
      </AppShell>
    </RequireRole>
  )
}
