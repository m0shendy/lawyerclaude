'use client'

// Schedule a new hearing — case picker + hearing details.
// POST /cases/{case_id}/hearings
// Supports ?case_id= pre-fill when navigating from a case detail page.

import { Suspense, useEffect, useState, type FormEvent } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ApiError, apiGet, apiPost } from '@/lib/api'
import { ALL_ROLES, RequireRole } from '@/lib/rbac'
import type { Case, User } from '@/lib/types'

// Inner component that uses useSearchParams — must be inside <Suspense>
function NewHearingForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const prefilledCaseId = searchParams.get('case_id') ?? ''

  const [cases, setCases] = useState<Case[]>([])
  const [lawyers, setLawyers] = useState<User[]>([])
  const [loadErr, setLoadErr] = useState<string | null>(null)

  // Form state
  const [caseId, setCaseId] = useState(prefilledCaseId)
  const [hearingDate, setHearingDate] = useState('')
  const [courtName, setCourtName] = useState('')
  const [courtRoom, setCourtRoom] = useState('')
  const [lawyerId, setLawyerId] = useState('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      apiGet<Case[]>('/cases'),
      apiGet<User[]>('/users'),
    ])
      .then(([c, u]) => {
        setCases(c)
        setLawyers(u.filter(u => u.role === 'lawyer' || u.role === 'partner_manager'))
      })
      .catch(e => setLoadErr(e instanceof ApiError ? e.message : 'تعذّر تحميل البيانات'))
  }, [])

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!caseId || !hearingDate || !courtName) return
    setBusy(true)
    setErr(null)
    try {
      const hearing = await apiPost<{ id: string }>(`/cases/${caseId}/hearings`, {
        hearing_date: new Date(hearingDate).toISOString(),
        court_name: courtName,
        court_room: courtRoom || null,
        assigned_lawyer_id: lawyerId || null,
        notes: notes || null,
      })
      router.push(`/hearings/${hearing.id}`)
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'تعذّر جدولة الجلسة')
      setBusy(false)
    }
  }

  const selectedCase = cases.find(c => c.id === caseId)

  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <div className="mb-6 flex items-center gap-3">
          <Link href="/hearings" className="text-sm text-gray-500 hover:text-gray-700">
            ← الجلسات
          </Link>
          <span className="text-gray-300">/</span>
          <h1 className="text-xl font-bold">جدولة جلسة جديدة</h1>
        </div>

        {loadErr && (
          <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{loadErr}</div>
        )}

        <form onSubmit={submit} className="max-w-xl space-y-5">
          {/* Case selector */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">القضية *</label>
            <select
              value={caseId}
              onChange={e => setCaseId(e.target.value)}
              required
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">— اختر قضية —</option>
              {cases.map(c => (
                <option key={c.id} value={c.id}>
                  {c.case_number ? `${c.case_number} — ` : ''}{c.title}
                </option>
              ))}
            </select>
            {selectedCase && (
              <p className="mt-1 text-xs text-gray-500">
                {selectedCase.client_name} · {selectedCase.stage}
              </p>
            )}
          </div>

          {/* Date + time */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">تاريخ ووقت الجلسة *</label>
            <input
              type="datetime-local"
              value={hearingDate}
              onChange={e => setHearingDate(e.target.value)}
              required
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Court name */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">اسم المحكمة *</label>
            <input
              type="text"
              value={courtName}
              onChange={e => setCourtName(e.target.value)}
              required
              placeholder="محكمة الاستئناف القاهرة"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Court room */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">القاعة</label>
            <input
              type="text"
              value={courtRoom}
              onChange={e => setCourtRoom(e.target.value)}
              placeholder="12أ"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Assigned lawyer */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">المحامي المكلَّف</label>
            <select
              value={lawyerId}
              onChange={e => setLawyerId(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">— غير محدد —</option>
              {lawyers.map(u => (
                <option key={u.id} value={u.id}>{u.full_name}</option>
              ))}
            </select>
          </div>

          {/* Notes */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">ملاحظات</label>
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              rows={3}
              placeholder="مستجدات الجلسة، طلبات الدفاع..."
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {err && <p className="text-sm text-red-700">{err}</p>}

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={busy || !caseId || !hearingDate || !courtName}
              className="rounded-lg bg-blue-700 px-5 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-50"
            >
              {busy ? 'جارٍ الحفظ…' : 'جدولة الجلسة'}
            </button>
            <Link
              href="/hearings"
              className="rounded-lg border border-gray-300 px-5 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              إلغاء
            </Link>
          </div>
        </form>
      </AppShell>
    </RequireRole>
  )
}

// Page wrapper — useSearchParams requires Suspense in Next.js 14
export default function NewHearingPage() {
  return (
    <Suspense fallback={null}>
      <NewHearingForm />
    </Suspense>
  )
}
