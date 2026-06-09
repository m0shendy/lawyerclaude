'use client'

// Template editor + Generate Draft (spec 002 US4, T035).
// Fetches/edits a single template; "Generate Draft" calls POST /templates/{id}/generate.
// Every generated output is born draft_unreviewed and links to /ai-review [C-II].

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet, apiPatch, apiPost } from '@/lib/api'
import { RequireRole } from '@/lib/rbac'
import type { Case } from '@/lib/types'

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

interface GenerateResult {
  output_id: string
  review_state: string
  type: string
  preview: string
}

function TemplateEditorScreen() {
  const { id } = useParams<{ id: string }>()
  const [tpl, setTpl] = useState<Template | null>(null)
  const [cases, setCases] = useState<Case[]>([])

  // Edit fields
  const [nameAr, setNameAr] = useState('')
  const [name, setName] = useState('')
  const [category, setCategory] = useState('')
  const [content, setContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)

  // Generate
  const [caseId, setCaseId] = useState('')
  const [context, setContext] = useState('')
  const [generating, setGenerating] = useState(false)
  const [genResult, setGenResult] = useState<GenerateResult | null>(null)
  const [genErr, setGenErr] = useState<string | null>(null)

  useEffect(() => {
    apiGet<Template>(`/templates/${id}`).then(t => {
      setTpl(t)
      setNameAr(t.name_ar)
      setName(t.name)
      setCategory(t.category ?? '')
      setContent(t.content_template)
    }).catch(() => {})
    apiGet<Case[]>('/cases').then(setCases).catch(() => {})
  }, [id])

  async function save() {
    setSaving(true); setSaveMsg(null)
    try {
      const updated = await apiPatch<Template>(`/templates/${id}`, {
        name_ar: nameAr,
        name,
        category: category || null,
        content_template: content,
      })
      setTpl(updated)
      setSaveMsg('تم الحفظ ✓')
      setTimeout(() => setSaveMsg(null), 3000)
    } catch (e) {
      setSaveMsg(e instanceof ApiError ? e.message : 'تعذّر الحفظ')
    } finally { setSaving(false) }
  }

  async function generate() {
    if (!caseId) return
    setGenerating(true); setGenErr(null); setGenResult(null)
    try {
      const res = await apiPost<GenerateResult>(`/templates/${id}/generate`, {
        case_id: caseId,
        context: context || null,
      })
      setGenResult(res)
    } catch (e) {
      setGenErr(e instanceof ApiError ? e.message : 'تعذّر توليد المسودة')
    } finally { setGenerating(false) }
  }

  if (!tpl) return <p className="text-sm text-gray-400">جارٍ التحميل…</p>

  return (
    <>
      <div className="mb-4 flex items-center gap-3">
        <Link href="/documents/templates" className="text-sm text-gray-500 hover:text-gray-700">
          ← النماذج
        </Link>
        <span className="text-gray-300">/</span>
        <h1 className="text-xl font-bold">{tpl.name_ar}</h1>
      </div>

      {/* Edit form */}
      <div className="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-4">
        <h2 className="text-sm font-bold text-gray-700">تعديل النموذج</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <label className="text-sm">
            الاسم بالعربية *
            <input value={nameAr} onChange={e => setNameAr(e.target.value)}
              className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5 text-sm" />
          </label>
          <label className="text-sm">
            الاسم بالإنجليزية
            <input value={name} onChange={e => setName(e.target.value)}
              className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5 text-sm" />
          </label>
          <label className="text-sm">
            التصنيف
            <select value={category} onChange={e => setCategory(e.target.value)}
              className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5 text-sm">
              <option value="">— اختياري —</option>
              <option value="contract">عقد</option>
              <option value="submission">مذكرة قضائية</option>
              <option value="engagement_letter">خطاب توكيل</option>
              <option value="letter">خطاب رسمي</option>
              <option value="other">أخرى</option>
            </select>
          </label>
        </div>
        <label className="text-sm block">
          محتوى النموذج
          <p className="text-xs text-gray-400 mb-1">
            استخدم <code>{'{{variable}}'}</code> للمتغيرات و <code>{'{{AI: تعليمات}}'}</code> لتوليد AI
          </p>
          <textarea
            value={content}
            onChange={e => setContent(e.target.value)}
            rows={12}
            className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5 text-sm font-mono"
            dir="rtl"
          />
        </label>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving}
            className="rounded-lg bg-blue-700 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
          >
            {saving ? 'جارٍ الحفظ…' : 'حفظ التعديلات'}
          </button>
          {saveMsg && <span className="text-sm text-green-700">{saveMsg}</span>}
        </div>
      </div>

      {/* Generate draft */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-4">
        <h2 className="text-sm font-bold text-gray-700">توليد مسودة</h2>
        <p className="text-xs text-amber-700 bg-amber-50 rounded px-3 py-2 border border-amber-200">
          ⚠ كل المخرجات تُنشأ كمسودة بانتظار المراجعة — التصدير محظور قبل اعتماد محامٍ. {/* [C-II] */}
        </p>
        <div className="grid sm:grid-cols-2 gap-4">
          <label className="text-sm">
            القضية *
            <select value={caseId} onChange={e => setCaseId(e.target.value)}
              className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5 text-sm">
              <option value="">— اختر قضية —</option>
              {cases.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
            </select>
          </label>
          <label className="text-sm">
            تعليمات إضافية (اختياري)
            <input value={context} onChange={e => setContext(e.target.value)}
              className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5 text-sm" />
          </label>
        </div>
        <button
          type="button"
          onClick={() => void generate()}
          disabled={generating || !caseId}
          className="rounded-lg bg-green-700 px-5 py-2 text-sm font-semibold text-white hover:bg-green-800 disabled:opacity-50"
        >
          {generating ? 'جارٍ التوليد…' : '✨ توليد مسودة'}
        </button>
        {genErr && (
          <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{genErr}</div>
        )}
        {genResult && (
          <div className="rounded-lg border border-green-200 bg-green-50 p-4 space-y-2">
            <p className="text-sm font-semibold text-green-800">
              ✓ تم إنشاء المسودة — في انتظار المراجعة
            </p>
            <p className="text-xs text-gray-500 font-mono whitespace-pre-wrap leading-relaxed">
              {genResult.preview}
            </p>
            <Link
              href="/ai-review"
              className="inline-block rounded-lg bg-green-700 px-4 py-1.5 text-xs font-semibold text-white hover:bg-green-800"
            >
              اذهب إلى المراجعة →
            </Link>
          </div>
        )}
      </div>
    </>
  )
}

export default function TemplateEditorPage() {
  return (
    <RequireRole roles={['partner_manager', 'lawyer']}>
      <AppShell>
        <TemplateEditorScreen />
      </AppShell>
    </RequireRole>
  )
}
