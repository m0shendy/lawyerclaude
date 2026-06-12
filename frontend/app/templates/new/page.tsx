'use client'

import { useState, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import AppShell from '@/components/AppShell'
import { ApiError, apiPost } from '@/lib/api'
import { RequireRole } from '@/lib/rbac'
import { TEMPLATE_CATEGORY_LABELS, type TemplateCategory } from '@/lib/types'

const CATEGORIES: TemplateCategory[] = ['contract', 'letter', 'pleading', 'power_of_attorney', 'court_submission', 'notice', 'other']

export default function NewTemplatePage() {
  const router = useRouter()
  const [name, setName] = useState('')
  const [category, setCategory] = useState<TemplateCategory>('letter')
  const [description, setDescription] = useState('')
  const [content, setContent] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Extract merge fields from content ({{field_name}})
  const detectedFields = Array.from(new Set(
    Array.from(content.matchAll(/\{\{(\w+)\}\}/g)).map(m => m[1])
  ))

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!content.trim()) { setError('محتوى النموذج مطلوب'); return }
    setBusy(true)
    setError(null)
    try {
      const mergeFields = detectedFields.map(f => ({ key: f, label_ar: f, type: 'text' as const, required: true }))
      const created = await apiPost<{ id: string }>('/templates', {
        name_ar: name,
        category,
        description: description || null,
        content,
        merge_fields: mergeFields,
      })
      router.push(`/templates/${created.id}`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ غير متوقع')
    } finally {
      setBusy(false)
    }
  }

  const inp = 'w-full rounded border border-gray-300 px-3 py-2 text-sm'

  return (
    <RequireRole roles={['partner_manager']}>
      <AppShell>
        <div className="mx-auto max-w-3xl">
          <h1 className="mb-6 text-xl font-bold">نموذج جديد</h1>

          {error && <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>}

          <form onSubmit={onSubmit} className="space-y-5">
            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="sm:col-span-2">
                  <label className="mb-1 block text-sm font-medium">اسم النموذج *</label>
                  <input value={name} onChange={e => setName(e.target.value)} className={inp} required />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">النوع *</label>
                  <select value={category} onChange={e => setCategory(e.target.value as TemplateCategory)} className={inp}>
                    {CATEGORIES.map(c => <option key={c} value={c}>{TEMPLATE_CATEGORY_LABELS[c]}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">وصف مختصر</label>
                  <input value={description} onChange={e => setDescription(e.target.value)} className={inp} />
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium">محتوى النموذج *</label>
                <span className="text-xs text-gray-400">استخدم {'{{'} field_name {'}}' } للحقول القابلة للتعبئة</span>
              </div>
              <textarea
                value={content}
                onChange={e => setContent(e.target.value)}
                rows={16}
                className={`${inp} font-mono text-xs`}
                placeholder="أدخل نص النموذج هنا..."
                required
              />
              {detectedFields.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs font-medium text-gray-600 mb-1">الحقول المكتشفة تلقائياً:</p>
                  <div className="flex flex-wrap gap-1">
                    {detectedFields.map(f => (
                      <span key={f} className="rounded bg-blue-50 px-2 py-0.5 text-xs text-blue-700 font-mono">{f}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="flex gap-3">
              <button type="submit" disabled={busy} className="rounded bg-blue-700 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50">
                {busy ? 'جارٍ الحفظ…' : 'حفظ النموذج'}
              </button>
              <button type="button" onClick={() => router.back()} className="rounded border border-gray-300 px-5 py-2 text-sm hover:bg-gray-50">إلغاء</button>
            </div>
          </form>
        </div>
      </AppShell>
    </RequireRole>
  )
}
