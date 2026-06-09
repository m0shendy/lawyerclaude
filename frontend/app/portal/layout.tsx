'use client'

// Portal layout — role guard + minimal RTL shell for client-facing portal (T073).
// If the stored token carries a non-'client' role → redirect to /portal/login.
// Renders WITHOUT the main app sidebar; portal has its own bottom nav.
// Footer shows the mandatory assistive-tool disclaimer [C-VIII].

import { useEffect, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'

function parseJwtRole(token: string): string | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]!))
    // Supabase embeds role in `app_metadata` or directly in `role`
    return payload?.app_metadata?.role ?? payload?.role ?? null
  } catch {
    return null
  }
}

export default function PortalLayout({ children }: { children: ReactNode }) {
  const router = useRouter()

  useEffect(() => {
    const token = sessionStorage.getItem('portal_token') ?? localStorage.getItem('portal_token')
    if (!token) {
      router.replace('/portal/login')
      return
    }
    const role = parseJwtRole(token)
    // Internal users should use the main app; portal is client-only
    if (role !== null && role !== 'client') {
      router.replace('/dashboard')
    }
  }, [router])

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col" dir="rtl">
      {/* Top bar */}
      <header className="sticky top-0 z-20 border-b border-gray-200 bg-white px-4 py-3 flex items-center justify-between shadow-sm">
        <h1 className="text-base font-bold text-blue-800">بوابة العملاء</h1>
        <button
          type="button"
          onClick={() => {
            sessionStorage.removeItem('portal_token')
            localStorage.removeItem('portal_token')
            window.location.href = '/portal/login'
          }}
          className="text-xs text-gray-500 hover:text-gray-700"
        >
          تسجيل الخروج
        </button>
      </header>

      {/* Page content */}
      <main className="flex-1 p-4 pb-24">
        {children}
      </main>

      {/* Bottom navigation */}
      <nav className="fixed bottom-0 left-0 right-0 z-20 border-t border-gray-200 bg-white flex items-center justify-around py-2">
        {[
          { href: '/portal/dashboard', icon: '🏠', label: 'الرئيسية' },
          { href: '/portal/matters',   icon: '⚖️', label: 'القضايا' },
          { href: '/portal/documents', icon: '📁', label: 'المستندات' },
          { href: '/portal/invoices',  icon: '🧾', label: 'الفواتير' },
          { href: '/portal/profile',   icon: '👤', label: 'حسابي' },
        ].map(item => (
          <a key={item.href} href={item.href} className="flex flex-col items-center gap-0.5 text-gray-500 hover:text-blue-700">
            <span className="text-xl">{item.icon}</span>
            <span className="text-xs">{item.label}</span>
          </a>
        ))}
      </nav>

      {/* Assistive-tool disclaimer [C-VIII] */}
      <footer className="fixed bottom-14 left-0 right-0 px-4 py-1 bg-amber-50 border-t border-amber-100 text-center text-xs text-amber-700">
        هذا النظام أداة مساعدة للمحامين. المسؤولية المهنية تقع على عاتق المحامي.
      </footer>
    </div>
  )
}
