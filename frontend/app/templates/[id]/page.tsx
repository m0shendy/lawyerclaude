'use client'

import { useEffect, useState, type FormEvent } from 'react'
import { useParams, useRouter } from 'next/navigation'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet, apiPatch, apiPost, apiDelete } from '@/lib/api'
import { RequireRole, useUser, ALL_ROLES } from '@/lib/rbac'
import { TEMPLATE_CATEGORY_LABELS, type Template, type TemplateCategory } from '@/lib/types'

const CATEGORIES: TemplateCategory[] = ['contract', 'letter', 'pleading', 'power_of_attorney', 'court_submission', 'notice', 'other']

export default function TemplateDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { user } = useUser()
  const [tpl, setTpl] = useState<Template | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  // Edit form
  const [name_ar, setNameAr] = useState('')
  const [category, setCategory] = useState<TemplateCategory>('letter')
  const [content, setContent] = useState('')
  const [saveBusy, setSaveBusy] = useState(false)
  // Render form
  const [showRender, setShowRender] = useState(false)
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({})
  const [rendered, setRendered] = useState<string | null>(null)
  const [unresolved, setUnresolved] = useState<string[]>([])
  const [renderBusy, setRenderBusy] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const t = await apiGet<Template>(`/templates/${id}`)
      setTpl(t)
      setNameAr(t.name_ar); setCategory(t.category)
      setContent(t.content)
      // Init field values from merge_fields
      const init: Record<string, string> = {}
      t.merge_fields?.forEach(f => { init[f.key] = '' })
      setFieldValues(init)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [id])

  async function onSave(e: FormEvent) {
    e.preventDefault()
    setSaveBusy(true)
    setError(null)
    try {
      const detectedFields = Array.from(new Set(
        Array.from(content.matchAll(/\{\{(\w+)\}\}/g)).map(m => m[1])
      ))
      const mergeFields = detectedFields.map(f => ({
        key: f, label_ar: f, type: 'text' as const, required: true,
      }))
      await apiPatch(`/templates/${id}`, { name_ar, category, content, merge_fields: mergeFields })
      setEditing(false)
      load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    } finally {
      setSaveBusy(false)
    }
  }

  async function onRender(e: FormEvent) {
    e.preventDefault()
    setRenderBusy(true)
    setError(null)
    try {
      const res = await apiPost<{ rendered_text: string; unresolved_fields: string[] }>(`/templates/${id}/render`, {
        field_values: fieldValues,
        case_id: fieldValues['case_id'] || null,
      })
      setRendered(res.rendered_text)
      setUnresolved(res.unresolved_fields)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    } finally {
      setRenderBusy(false)
    }
  }

  async function onDelete() {
    if (!confirm('حذف هذا النموذج نهائياً؟')) return
    try {
      await apiDelete(`/templates/${id}`)
      router.push('/templates')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'حدث خطأ')
    }
  }

  if (loading) return <AppShell><p className="text-sm text-gray-500">جارٍ التحميل…</p></AppShell>
  if (!tpl) return <AppShell><p className="text-sm text-red-600">{error}</p></AppShell>

  const isManager = user?.role === 'partner_manager'
  const inp = 'w-full rounded border border-gray-300 px-3 py-2 text-sm'

  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <div className="mx-auto max-w-3xl">
          {/* Header */}
          <div className="flex items-start justify-between mb-6">
            <div>
              <h1 className="text-xl font-bold">{tpl.name_ar}</h1>
              <div className="flex items-center gap-2 mt-1">
                <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                  {TEMPLATE_CATEGORY_LABELS[tpl.category]}
                </span>
                <span className="text-xs text-gray-400">v{tpl.version}</span>
              </div>
            </div>
            {isManager && (
              <div className="flex gap-2">
                <button onClick={() => setEditing(v => !v)} className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50">
                  {editing ? 'إلغاء التعديل' : 'تعديل'}
                </button>
                <button onClick={onDelete} className="rounded border border-red-200 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50">حذف</button>
              </div>
            )}
          </div>

          {error && <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>}

          {/* Edit form */}
          {editing ? (
            <form onSubmit={onSave} className="space-y-4 mb-6">
              <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-3">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="sm:col-span-2">
                    <label className="mb-1 block text-xs font-medium">اسم النموذج *</label>
                    <input value={name_ar} onChange={e => setNameAr(e.target.value)} className={inp} required />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium">النوع</label>
                    <select value={category} onChange={e => setCategory(e.target.value as TemplateCategory)} className={inp}>
                      {CATEGORIES.map(c => <option key={c} value={c}>{TEMPLATE_CATEGORY_LABELS[c]}</option>)}
                    </select>
                  </div>

                  <div className="sm:col-span-2">
                    <label className="mb-1 block text-xs font-medium">المحتوى</label>
                    <textarea value={content} onChange={e => setContent(e.target.value)} rows={14} className={`${inp} font-mono text-xs`} />
                  </div>
                </div>
                <div className="flex gap-2">
                  <button type="submit" disabled={saveBusy} className="rounded bg-blue-700 px-4 py-2 text-sm text-white hover:bg-blue-800 disabled:opacity-50">
                    {saveBusy ? 'جارٍ الحفظ…' : 'حفظ'}
                  </button>
                  <button type="button" onClick={() => setEditing(false)} className="rounded border border-gray-300 px-4 py-2 text-sm">إلغاء</button>
                </div>
              </div>
            </form>
          ) : (
            /* Content preview */
            <div className="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="text-sm font-semibold mb-3">محتوى النموذج</h2>
              <pre className="whitespace-pre-wrap text-xs text-gray-700 font-sans leading-relaxed">{tpl.content}</pre>
              {tpl.merge_fields && tpl.merge_fields.length > 0 && (
                <div className="mt-4 pt-4 border-t border-gray-100">
                  <p className="text-xs font-medium text-gray-600 mb-2">حقول التعبئة:</p>
                  <div className="flex flex-wrap gap-1">
                    {tpl.merge_fields.map(f => (
                      <span key={f.key} className="rounded bg-blue-50 px-2 py-0.5 text-xs text-blue-700 font-mono">{f.key}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Render section */}
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold">استخدام النموذج</h2>
              <button onClick={() => setShowRender(v => !v)} className="text-xs text-blue-700 hover:underline">
                {showRender ? 'إخفاء' : 'تعبئة النموذج'}
              </button>
            </div>

            {showRender && (
              <form onSubmit={onRender} className="space-y-3">
                {tpl.merge_fields && tpl.merge_fields.length > 0 ? (
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {tpl.merge_fields.map(f => (
                      <div key={f.key}>
                        <label className="mb-1 block text-xs font-medium">{f.label_ar ?? f.key}</label>
                        <input
                          value={fieldValues[f.key] ?? ''}
                          onChange={e => setFieldValues(v => ({ ...v, [f.key]: e.target.value }))}
                          className={inp}
                          placeholder={f.key}
                        />
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-500">لا توجد حقول تعبئة في هذا النموذج</p>
                )}
                <button type="submit" disabled={renderBusy} className="rounded bg-green-700 px-4 py-2 text-sm text-white hover:bg-green-800 disabled:opacity-50">
                  {renderBusy ? 'جارٍ التعبئة…' : 'معاينة النص المُعبَّأ'}
                </button>
              </form>
            )}

            {rendered && (
              <div className="mt-4">
                {unresolved.length > 0 && (
                  <div className="mb-3 rounded bg-yellow-50 px-3 py-2 text-xs text-yellow-800">
                    حقول لم تُعبَّأ: {unresolved.map(f => <code key={f} className="mx-0.5 font-mono">{'{{'}{f}{'}}'}</code>)}
                  </div>
                )}
                <p className="text-xs font-medium text-gray-600 mb-2">النص المُعبَّأ:</p>
                <pre className="whitespace-pre-wrap rounded bg-gray-50 p-4 text-xs text-gray-800 font-sans leading-relaxed border border-gray-200">
                  {rendered}
                </pre>
                <button
                  onClick={() => navigator.clipboard.writeText(rendered)}
                  className="mt-2 rounded border border-gray-300 px-3 py-1.5 text-xs hover:bg-gray-50"
                >
                  نسخ النص
                </button>
              </div>
            )}
          </div>
        </div>
      </AppShell>
    </RequireRole>
  )
}
