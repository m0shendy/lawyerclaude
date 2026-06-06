'use client'

// Settings screen (manager only). [C-III][C-XI]
// Secrets (waha_key, llm_api_key) are never echoed by the API — the screen
// shows "••••••••" when a secret is stored and lets the manager overwrite it.
// The audit trigger logs changes as "[REDACTED]", never the actual value. [C-III]

import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '@/components/AppShell'
import { MANAGER_ONLY, RequireRole } from '@/lib/rbac'
import { apiGet, apiPatch, ApiError } from '@/lib/api'
import type { FirmSettings } from '@/lib/types'

const SECRET_PLACEHOLDER = '••••••••'

function SettingsScreen() {
  const [settings, setSettings] = useState<FirmSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  // form fields
  const [firmName, setFirmName] = useState('')
  const [wahaUrl, setWahaUrl] = useState('')
  const [wahaKey, setWahaKey] = useState('')      // blank = do not change if set
  const [llmKey, setLlmKey] = useState('')        // blank = do not change if set
  const [embedModel, setEmbedModel] = useState('')
  const [embedDim, setEmbedDim] = useState(1536)
  const [leadPoints, setLeadPoints] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    apiGet<FirmSettings>('/settings')
      .then((s) => {
        setSettings(s)
        setFirmName(s.firm_name)
        setWahaUrl(s.waha_url ?? '')
        setWahaKey(s.waha_key_set ? SECRET_PLACEHOLDER : '')
        setLlmKey(s.llm_api_key_set ? SECRET_PLACEHOLDER : '')
        setEmbedModel(s.embedding_config?.model ?? '')
        setEmbedDim(s.embedding_config?.dimension ?? 1536)
        setLeadPoints(s.reminder_lead_points?.join(', ') ?? '7d, 3d, 1d, 0d')
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'تعذّر تحميل الإعدادات'))
      .finally(() => setLoading(false))
  }, [])

  async function onSave(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setSuccess(false)
    try {
      const leadArr = leadPoints
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)

      const body: Record<string, unknown> = {
        firm_name: firmName,
        waha_url: wahaUrl || null,
        embedding_config: { model: embedModel, dimension: embedDim },
        reminder_lead_points: leadArr,
      }
      // Only send secret fields if the user typed a NEW value.
      // Sending the sentinel placeholder back means "leave unchanged"
      // (the backend will ignore it). Empty string clears the secret.
      if (wahaKey !== SECRET_PLACEHOLDER) body.waha_key = wahaKey || ''
      if (llmKey !== SECRET_PLACEHOLDER) body.llm_api_key = llmKey || ''

      const updated = await apiPatch<FirmSettings>('/settings', body)
      setSettings(updated)
      // Refresh sentinel state after save.
      setWahaKey(updated.waha_key_set ? SECRET_PLACEHOLDER : '')
      setLlmKey(updated.llm_api_key_set ? SECRET_PLACEHOLDER : '')
      setSuccess(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'تعذّر حفظ الإعدادات')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <p className="p-8 text-sm text-gray-500">جارٍ تحميل الإعدادات…</p>
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-6 text-2xl font-bold">إعدادات المكتب</h1>

      {error && (
        <div className="mb-4 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </div>
      )}
      {success && (
        <div className="mb-4 rounded border border-green-300 bg-green-50 px-3 py-2 text-sm text-green-800">
          تم حفظ الإعدادات بنجاح.
        </div>
      )}

      <form onSubmit={onSave} className="space-y-6">

        {/* ── هوية المكتب ───────────────────────────────────────── */}
        <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 font-semibold text-gray-800">هوية المكتب</h2>
          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="firmName">
              اسم المكتب
            </label>
            <input
              id="firmName"
              value={firmName}
              onChange={(e) => setFirmName(e.target.value)}
              className="w-full rounded border border-gray-300 px-3 py-2"
            />
          </div>
        </section>

        {/* ── واتساب (WAHA) ────────────────────────────────────────── */}
        <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 font-semibold text-gray-800">واتساب — WAHA</h2>
          <p className="mb-4 text-xs text-gray-500">
            مفتاح API سرّي — يُسجَّل التغيير في سجل التدقيق كـ «تم التغيير» دون الكشف عن القيمة.
          </p>
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-sm font-medium" htmlFor="wahaUrl">
                رابط WAHA (URL)
              </label>
              <input
                id="wahaUrl"
                type="url"
                value={wahaUrl}
                onChange={(e) => setWahaUrl(e.target.value)}
                placeholder="https://waha.example.com"
                className="w-full rounded border border-gray-300 px-3 py-2 font-mono text-sm"
                dir="ltr"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium" htmlFor="wahaKey">
                مفتاح WAHA API
                {settings?.waha_key_set && (
                  <span className="mr-2 text-xs text-green-700">● مضبوط</span>
                )}
              </label>
              <input
                id="wahaKey"
                type="password"
                value={wahaKey}
                onChange={(e) => setWahaKey(e.target.value)}
                placeholder={settings?.waha_key_set ? SECRET_PLACEHOLDER : 'أدخل مفتاح API'}
                className="w-full rounded border border-gray-300 px-3 py-2 font-mono text-sm"
                dir="ltr"
                autoComplete="new-password"
              />
              <p className="mt-1 text-xs text-gray-400">
                اتركه كما هو لعدم التغيير. مسحه بالكامل يحذف المفتاح المخزَّن.
              </p>
            </div>
          </div>
        </section>

        {/* ── مفتاح الذكاء الاصطناعي ───────────────────────────────── */}
        <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 font-semibold text-gray-800">الذكاء الاصطناعي — مفتاح API</h2>
          <p className="mb-4 text-xs text-gray-500">
            مفتاح Gemini (أو OpenAI) الخاص بالعميل — سرّي ومُعالَج كالمفتاح أعلاه.
          </p>
          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="llmKey">
              مفتاح LLM API
              {settings?.llm_api_key_set && (
                <span className="mr-2 text-xs text-green-700">● مضبوط</span>
              )}
            </label>
            <input
              id="llmKey"
              type="password"
              value={llmKey}
              onChange={(e) => setLlmKey(e.target.value)}
              placeholder={settings?.llm_api_key_set ? SECRET_PLACEHOLDER : 'أدخل مفتاح API'}
              className="w-full rounded border border-gray-300 px-3 py-2 font-mono text-sm"
              dir="ltr"
              autoComplete="new-password"
            />
          </div>
        </section>

        {/* ── إعداد التضمين ────────────────────────────────────────── */}
        <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 font-semibold text-gray-800">إعداد التضمين (Embedding)</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium" htmlFor="embedModel">
                النموذج
              </label>
              <input
                id="embedModel"
                value={embedModel}
                onChange={(e) => setEmbedModel(e.target.value)}
                placeholder="gemini-embedding-001"
                className="w-full rounded border border-gray-300 px-3 py-2 font-mono text-sm"
                dir="ltr"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium" htmlFor="embedDim">
                الأبعاد
              </label>
              <input
                id="embedDim"
                type="number"
                value={embedDim}
                onChange={(e) => setEmbedDim(Number(e.target.value))}
                min={256}
                max={4096}
                className="w-full rounded border border-gray-300 px-3 py-2"
                dir="ltr"
              />
            </div>
          </div>
        </section>

        {/* ── نقاط تذكير المواعيد ──────────────────────────────────── */}
        <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 font-semibold text-gray-800">نقاط تذكير المواعيد</h2>
          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="leadPoints">
              الفترات (مفصولة بفاصلة، مثل: 7d, 3d, 1d, 0d)
            </label>
            <input
              id="leadPoints"
              value={leadPoints}
              onChange={(e) => setLeadPoints(e.target.value)}
              placeholder="7d, 3d, 1d, 0d"
              className="w-full rounded border border-gray-300 px-3 py-2 font-mono text-sm"
              dir="ltr"
            />
            <p className="mt-1 text-xs text-gray-400">
              «0d» = نفس اليوم · «1d» = قبل يوم · «7d» = قبل أسبوع
            </p>
          </div>
        </section>

        <div className="flex items-center gap-4 pb-8">
          <button
            type="submit"
            disabled={saving}
            className="rounded bg-blue-700 px-6 py-2.5 font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
          >
            {saving ? 'جارٍ الحفظ…' : 'حفظ الإعدادات'}
          </button>
          {settings && (
            <p className="text-xs text-gray-400">
              آخر تعديل: {new Date(settings.updated_at).toLocaleString('ar-EG')}
            </p>
          )}
        </div>
      </form>
    </div>
  )
}

export default function SettingsPage() {
  return (
    <RequireRole roles={MANAGER_ONLY}>
      <AppShell>
        <SettingsScreen />
      </AppShell>
    </RequireRole>
  )
}
