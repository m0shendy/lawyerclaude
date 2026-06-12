'use client'

// Operator shell layout — completely separate from the firm AppNav.
// No firm nav component is imported here; operators cannot "wander" into
// firm screens, and firm users never see admin nav items. [C-I]

import type { ReactNode } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import { adminGet, clearOperatorToken } from '@/lib/adminApi'

interface OperatorInfo {
  operator_id: string
  display_name: string
  session_created_at: string
}

const NAV = [
  { href: '/admin',         label: 'لوحة المكاتب' },
  { href: '/admin/billing', label: 'الفوترة' },
  { href: '/admin/audit',   label: 'سجل التدقيق' },
  { href: '/admin/health',  label: 'الحالة التشغيلية' },
]

export default function AdminLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const [operator, setOperator] = useState<OperatorInfo | null>(null)
  const [checked, setChecked] = useState(false)

  useEffect(() => {
    if (pathname === '/admin/login') {
      setChecked(true)
      return
    }
    adminGet<OperatorInfo>('/admin/me')
      .then((data) => { setOperator(data); setChecked(true) })
      .catch(() => {
        // 401 → adminGet already redirects; this catches network errors
        setChecked(true)
      })
  }, [pathname])

  // On the login page render children directly (no nav shell needed)
  if (pathname === '/admin/login') return <>{children}</>

  // Session guard: redirect happens inside adminApi on 401;
  // while checking show nothing to avoid flash
  if (!checked) return null

  async function handleLogout() {
    try {
      await adminGet('/admin/logout', { method: 'POST' })
    } finally {
      clearOperatorToken()
      window.location.href = '/admin/login'
    }
  }

  return (
    <div className="flex min-h-screen bg-gray-50" dir="rtl">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 border-l border-gray-200 bg-white">
        <div className="border-b border-gray-200 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-gray-400">لوحة المشغّل</p>
          {operator && (
            <p className="mt-1 truncate text-sm font-medium text-gray-700">{operator.display_name}</p>
          )}
        </div>
        <nav className="p-2">
          {NAV.map((item) => {
            const active =
              item.href === '/admin'
                ? pathname === '/admin'
                : pathname.startsWith(item.href)
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`block rounded px-3 py-2 text-sm ${
                  active
                    ? 'bg-blue-50 font-semibold text-blue-700'
                    : 'text-gray-700 hover:bg-gray-100'
                }`}
              >
                {item.label}
              </Link>
            )
          })}
        </nav>
        <div className="absolute bottom-4 px-4">
          <button
            onClick={handleLogout}
            className="text-xs text-gray-400 hover:text-red-600"
          >
            تسجيل الخروج
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto p-6">{children}</main>
    </div>
  )
}
