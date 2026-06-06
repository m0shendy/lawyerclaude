'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

interface PortalCase {
  id: string
  case_number: string | null
  title: string
  status: string
  court_name: string | null
  hearing_count: number
}

interface PortalInvoice {
  id: string
  invoice_number: string
  total_egp: string
  amount_due: string
  status: string
  due_date: string
}

async function portalGet<T>(path: string, token: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? 'خطأ')
  return res.json() as Promise<T>
}

export default function PortalDashboardPage() {
  const router = useRouter()
  const [cases, setCases] = useState<PortalCase[]>([])
  const [invoices, setInvoices] = useState<PortalInvoice[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const token = sessionStorage.getItem('portal_token')
    if (!token) { router.replace('/portal/login'); return }

    Promise.all([
      portalGet<PortalCase[]>('/portal/cases', token),
      portalGet<PortalInvoice[]>('/portal/invoices', token),
    ])
      .then(([c, i]) => { setCases(c); setInvoices(i) })
      .catch(e => {
        if (e.message?.includes('401') || e.message?.includes('Unauthorized')) {
          sessionStorage.removeItem('portal_token')
          router.replace('/portal/login')
        } else {
          setError(e.message ?? 'حدث خطأ')
        }
      })
      .finally(() => setLoading(false))
  }, [])

  function logout() {
    sessionStorage.removeItem('portal_token')
    router.push('/portal/login')
  }

  const CASE_STATUS_AR: Record<string, string> = {
    open: 'مفتوحة', active: 'نشطة', closed: 'مغلقة', on_hold: 'معلّقة', archived: 'مؤرشفة',
  }

  const INVOICE_STATUS_AR: Record<string, string> = {
    draft: 'مسودة', sent: 'مُرسَلة', partial: 'مدفوعة جزئياً', paid: 'مدفوعة', overdue: 'متأخرة', cancelled: 'ملغية',
  }

  const overdueInvoices = invoices.filter(i => i.status === 'overdue')
  const unpaidInvoices = invoices.filter(i => ['sent', 'partial', 'overdue'].includes(i.status))

  return (
    <div className="min-h-screen bg-gray-50" dir="rtl">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white px-4 py-4">
        <div className="mx-auto max-w-3xl flex items-center justify-between">
          <h1 className="text-lg font-bold">بوابة العملاء</h1>
          <button onClick={logout} className="text-sm text-gray-500 hover:text-gray-700">خروج</button>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-6 space-y-6">
        {error && <div className="rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>}

        {loading ? (
          <p className="text-sm text-gray-500">جارٍ التحميل…</p>
        ) : (
          <>
            {/* Overdue alert */}
            {overdueInvoices.length > 0 && (
              <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                لديك {overdueInvoices.length} فاتورة متأخرة. يُرجى التواصل مع مكتب المحاماة.
              </div>
            )}

            {/* Summary cards */}
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm text-center">
                <p className="text-2xl font-bold text-blue-700">{cases.length}</p>
                <p className="text-xs text-gray-500 mt-1">قضية</p>
              </div>
              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm text-center">
                <p className="text-2xl font-bold text-orange-600">{unpaidInvoices.length}</p>
                <p className="text-xs text-gray-500 mt-1">فاتورة غير مسدّدة</p>
              </div>
            </div>

            {/* Cases */}
            <section>
              <h2 className="text-base font-semibold mb-3">قضاياي</h2>
              {cases.length === 0 ? (
                <p className="text-sm text-gray-500">لا توجد قضايا مرتبطة بحسابك</p>
              ) : (
                <div className="space-y-2">
                  {cases.map(c => (
                    <Link
                      key={c.id}
                      href={`/portal/cases/${c.id}`}
                      className="flex items-center justify-between rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm hover:shadow"
                    >
                      <div>
                        <p className="font-medium text-sm">{c.title}</p>
                        <p className="text-xs text-gray-400">{c.case_number} {c.court_name ? `· ${c.court_name}` : ''}</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-gray-500">{c.hearing_count} جلسة</span>
                        <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
                          {CASE_STATUS_AR[c.status] ?? c.status}
                        </span>
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </section>

            {/* Invoices */}
            <section>
              <h2 className="text-base font-semibold mb-3">فواتيري</h2>
              {invoices.length === 0 ? (
                <p className="text-sm text-gray-500">لا توجد فواتير</p>
              ) : (
                <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 text-right">
                      <tr>
                        <th className="px-4 py-2 font-semibold">رقم الفاتورة</th>
                        <th className="px-4 py-2 font-semibold">الإجمالي</th>
                        <th className="px-4 py-2 font-semibold">المتبقي</th>
                        <th className="px-4 py-2 font-semibold">الاستحقاق</th>
                        <th className="px-4 py-2 font-semibold">الحالة</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {invoices.map(inv => (
                        <tr key={inv.id} className={inv.status === 'overdue' ? 'bg-red-50' : ''}>
                          <td className="px-4 py-2 font-mono text-xs">{inv.invoice_number}</td>
                          <td className="px-4 py-2">{Number(inv.total_egp).toLocaleString('ar-EG')} ج.م</td>
                          <td className="px-4 py-2 font-medium">{Number(inv.amount_due).toLocaleString('ar-EG')} ج.م</td>
                          <td className="px-4 py-2 text-gray-500">{inv.due_date}</td>
                          <td className="px-4 py-2">
                            <span className={`rounded-full px-2 py-0.5 text-xs ${inv.status === 'paid' ? 'bg-green-50 text-green-700' : inv.status === 'overdue' ? 'bg-red-100 text-red-700' : 'bg-yellow-50 text-yellow-700'}`}>
                              {INVOICE_STATUS_AR[inv.status] ?? inv.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  )
}
