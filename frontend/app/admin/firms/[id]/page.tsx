'use client'

// Firm detail + lifecycle actions (T018 US2 / T021 US3).
// Every lifecycle action is behind a confirm dialog naming the firm + consequence.
// No work-product fields are displayed anywhere on this page. [FR-310][FR-312]

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { adminGet, adminPost } from '@/lib/adminApi'

interface FirmUsage {
  user_count: number
  case_count: number
  document_count: number
  storage_bytes: number
  ai_output_count: number
  last_activity_at: string | null
}

interface FirmDetail {
  id: string
  name: string
  slug: string
  status: string
  plan: string | null
  trial_ends_at: string | null
  created_at: string
  subscription: {
    plan: string
    status: string
    current_period_end: string | null
    provider: string
  } | null
  usage: FirmUsage
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

interface ConfirmDialogProps {
  firmName: string
  action: string
  consequence: string
  extraField?: { label: string; type: 'number' | 'select'; options?: string[]; value: string; onChange: (v: string) => void }
  onConfirm: () => void
  onCancel: () => void
  busy: boolean
}

function ConfirmDialog({ firmName, action, consequence, extraField, onConfirm, onCancel, busy }: ConfirmDialogProps) {
  const [checked, setChecked] = useState(false)
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" dir="rtl">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-2 text-lg font-bold">{action}</h2>
        <p className="mb-1 text-sm text-gray-600">
          المكتب: <span className="font-semibold">{firmName}</span>
        </p>
        <p className="mb-4 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {consequence}
        </p>
        {extraField && (
          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium">{extraField.label}</label>
            {extraField.type === 'number' ? (
              <input
                type="number"
                min={1}
                max={90}
                value={extraField.value}
                onChange={(e) => extraField.onChange(e.target.value)}
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              />
            ) : (
              <select
                value={extraField.value}
                onChange={(e) => extraField.onChange(e.target.value)}
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              >
                {extraField.options?.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            )}
          </div>
        )}
        <label className="mb-4 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
          أؤكد إجراء هذه العملية
        </label>
        <div className="flex gap-2">
          <button
            disabled={!checked || busy}
            onClick={onConfirm}
            className="flex-1 rounded bg-red-600 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
          >
            {busy ? 'جارٍ التنفيذ…' : 'تأكيد'}
          </button>
          <button
            onClick={onCancel}
            className="flex-1 rounded border border-gray-300 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            إلغاء
          </button>
        </div>
      </div>
    </div>
  )
}

type DialogType = 'suspend' | 'reactivate' | 'cancel' | 'extend_trial' | 'change_plan' | null

export default function FirmDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const [firm, setFirm] = useState<FirmDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dialog, setDialog] = useState<DialogType>(null)
  const [dialogBusy, setDialogBusy] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [trialDays, setTrialDays] = useState('7')
  const [newPlan, setNewPlan] = useState('basic')

  async function loadFirm() {
    setLoading(true)
    try {
      const data = await adminGet<FirmDetail>(`/admin/firms/${id}`)
      setFirm(data)
      setNewPlan(data.plan ?? 'basic')
    } catch {
      setError('فشل تحميل بيانات المكتب')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadFirm() }, [id])

  function showToast(msg: string) {
    setToast(msg)
    setTimeout(() => setToast(null), 4000)
  }

  async function doAction(path: string, body: Record<string, unknown>) {
    setDialogBusy(true)
    try {
      await adminPost(`/admin/firms/${id}/${path}`, { ...body, confirm: true })
      setDialog(null)
      showToast('تم تنفيذ الإجراء بنجاح — تم تسجيل الإجراء في سجل التدقيق')
      await loadFirm()
    } catch (err: unknown) {
      const e = err as { message?: string }
      setDialog(null)
      setError(e.message ?? 'حدث خطأ أثناء التنفيذ')
    } finally {
      setDialogBusy(false)
    }
  }

  if (loading) return <div dir="rtl" className="p-6 text-sm text-gray-400">جارٍ التحميل…</div>
  if (!firm) return <div dir="rtl" className="p-6 text-sm text-red-600">{error ?? 'المكتب غير موجود'}</div>

  return (
    <div dir="rtl">
      {toast && (
        <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white shadow-lg">
          {toast}
        </div>
      )}

      <button onClick={() => router.push('/admin')} className="mb-4 text-sm text-blue-600 hover:underline">
        ← العودة إلى لوحة المكاتب
      </button>

      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      {/* Firm card */}
      <div className="mb-4 rounded-xl border border-gray-200 bg-white p-5">
        <div className="mb-3 flex items-center justify-between">
          <h1 className="text-xl font-bold">{firm.name}</h1>
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${STATUS_COLOR[firm.status] ?? 'bg-gray-100 text-gray-600'}`}>
            {STATUS_LABEL[firm.status] ?? firm.status}
          </span>
        </div>
        <dl className="grid grid-cols-2 gap-2 text-sm">
          <div><dt className="text-gray-400">المعرف</dt><dd className="font-mono ltr">{firm.slug}</dd></div>
          <div><dt className="text-gray-400">تاريخ التسجيل</dt><dd>{new Date(firm.created_at).toLocaleDateString('ar-EG')}</dd></div>
          <div><dt className="text-gray-400">الخطة</dt><dd>{firm.plan ?? '—'}</dd></div>
          <div>
            <dt className="text-gray-400">انتهاء التجربة</dt>
            <dd>{firm.trial_ends_at ? new Date(firm.trial_ends_at).toLocaleDateString('ar-EG') : '—'}</dd>
          </div>
        </dl>
      </div>

      {/* Usage counts panel — counts only, no content */}
      <div className="mb-4 rounded-xl border border-gray-200 bg-white p-5">
        <h2 className="mb-3 font-semibold">إحصائيات الاستخدام</h2>
        <div className="grid grid-cols-3 gap-3 text-center">
          {[
            { label: 'مستخدمون', value: firm.usage.user_count },
            { label: 'قضايا', value: firm.usage.case_count },
            { label: 'مستندات', value: firm.usage.document_count },
            { label: 'مخرجات AI', value: firm.usage.ai_output_count },
            { label: 'آخر نشاط', value: firm.usage.last_activity_at ? new Date(firm.usage.last_activity_at).toLocaleDateString('ar-EG') : '—' },
          ].map(({ label, value }) => (
            <div key={label} className="rounded border border-gray-100 bg-gray-50 p-3">
              <p className="text-lg font-bold">{value}</p>
              <p className="text-xs text-gray-400">{label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Subscription panel */}
      {firm.subscription && (
        <div className="mb-4 rounded-xl border border-gray-200 bg-white p-5">
          <h2 className="mb-3 font-semibold">الاشتراك</h2>
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <div><dt className="text-gray-400">مزود الدفع</dt><dd>{firm.subscription.provider}</dd></div>
            <div><dt className="text-gray-400">حالة الاشتراك</dt><dd>{firm.subscription.status}</dd></div>
            <div>
              <dt className="text-gray-400">نهاية الفترة الحالية</dt>
              <dd>{firm.subscription.current_period_end ? new Date(firm.subscription.current_period_end).toLocaleDateString('ar-EG') : '—'}</dd>
            </div>
          </dl>
        </div>
      )}

      {/* Lifecycle actions */}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <h2 className="mb-3 font-semibold">إجراءات دورة الحياة</h2>
        <div className="flex flex-wrap gap-2">
          {firm.status !== 'suspended' && firm.status !== 'cancelled' && (
            <button onClick={() => setDialog('suspend')}
              className="rounded border border-red-200 bg-red-50 px-3 py-1.5 text-sm text-red-700 hover:bg-red-100">
              إيقاف تشغيل
            </button>
          )}
          {(firm.status === 'suspended' || firm.status === 'past_due') && (
            <button onClick={() => setDialog('reactivate')}
              className="rounded border border-green-200 bg-green-50 px-3 py-1.5 text-sm text-green-700 hover:bg-green-100">
              إعادة تفعيل
            </button>
          )}
          {firm.status !== 'cancelled' && (
            <button onClick={() => setDialog('cancel')}
              className="rounded border border-gray-200 bg-gray-50 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100">
              إلغاء الاشتراك
            </button>
          )}
          {firm.status !== 'cancelled' && (
            <button onClick={() => setDialog('extend_trial')}
              className="rounded border border-blue-200 bg-blue-50 px-3 py-1.5 text-sm text-blue-700 hover:bg-blue-100">
              تمديد التجربة
            </button>
          )}
          {firm.plan && (
            <button onClick={() => setDialog('change_plan')}
              className="rounded border border-purple-200 bg-purple-50 px-3 py-1.5 text-sm text-purple-700 hover:bg-purple-100">
              تغيير الخطة
            </button>
          )}
        </div>
      </div>

      {/* Dialogs */}
      {dialog === 'suspend' && (
        <ConfirmDialog
          firmName={firm.name}
          action="إيقاف تشغيل المكتب"
          consequence="سيُمنع موظفو المكتب من الدخول فورًا. يمكن إعادة التفعيل لاحقاً."
          onConfirm={() => doAction('suspend', {})}
          onCancel={() => setDialog(null)}
          busy={dialogBusy}
        />
      )}
      {dialog === 'reactivate' && (
        <ConfirmDialog
          firmName={firm.name}
          action="إعادة تفعيل المكتب"
          consequence="ستُستعاد صلاحيات الوصول للموظفين فوراً."
          onConfirm={() => doAction('reactivate', {})}
          onCancel={() => setDialog(null)}
          busy={dialogBusy}
        />
      )}
      {dialog === 'cancel' && (
        <ConfirmDialog
          firmName={firm.name}
          action="إلغاء اشتراك المكتب"
          consequence="سيتم إلغاء الاشتراك نهائياً. لا يمكن التراجع عن هذه الخطوة."
          onConfirm={() => doAction('cancel', {})}
          onCancel={() => setDialog(null)}
          busy={dialogBusy}
        />
      )}
      {dialog === 'extend_trial' && (
        <ConfirmDialog
          firmName={firm.name}
          action="تمديد فترة التجربة"
          consequence="سيتم إضافة الأيام المحددة إلى تاريخ انتهاء التجربة الحالي."
          extraField={{ label: 'عدد الأيام (1-90)', type: 'number', value: trialDays, onChange: setTrialDays }}
          onConfirm={() => doAction('extend-trial', { days: parseInt(trialDays, 10) })}
          onCancel={() => setDialog(null)}
          busy={dialogBusy}
        />
      )}
      {dialog === 'change_plan' && (
        <ConfirmDialog
          firmName={firm.name}
          action="تغيير خطة الاشتراك"
          consequence="سيتم تحديث الخطة إدارياً فقط — لن يتم تحريك أي مدفوعات."
          extraField={{ label: 'الخطة الجديدة', type: 'select', options: ['basic', 'pro', 'enterprise'], value: newPlan, onChange: setNewPlan }}
          onConfirm={() => doAction('change-plan', { plan: newPlan })}
          onCancel={() => setDialog(null)}
          busy={dialogBusy}
        />
      )}
    </div>
  )
}
