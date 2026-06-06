'use client'

// Role-aware sidebar navigation (RTL).

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useUser } from '@/lib/rbac'
import { signOut } from '@/lib/supabase'
import { ROLE_LABELS, type Role } from '@/lib/types'

interface NavItem {
  href: string
  label: string
  roles: Role[]
}

const ALL: Role[] = ['partner_manager', 'lawyer', 'paralegal', 'secretary']

const NAV: NavItem[] = [
  { href: '/dashboard',  label: 'لوحة المتابعة',       roles: ALL },
  { href: '/cases',      label: 'القضايا',              roles: ALL },
  { href: '/hearings',   label: 'الجلسات',              roles: ALL },
  { href: '/contacts',   label: 'الأطراف والجهات',      roles: ALL },
  { href: '/documents',  label: 'المستندات',            roles: ALL },
  { href: '/templates',  label: 'نماذج المستندات',      roles: ALL },
  { href: '/deadlines',  label: 'المواعيد',             roles: ALL },
  { href: '/tasks',      label: 'المهام',               roles: ['partner_manager', 'lawyer', 'paralegal'] },
  { href: '/billing',    label: 'الفواتير والأتعاب',    roles: ['partner_manager', 'secretary'] },
  { href: '/ai-review',  label: 'مراجعة الذكاء',       roles: ALL },
  { href: '/assistant',  label: 'المساعد الذكي',        roles: ALL },
  { href: '/references', label: 'المراجع القانونية',    roles: ALL },
  { href: '/analytics',  label: 'التقارير المالية',     roles: ['partner_manager'] },
  { href: '/reports',    label: 'التقارير الإدارية',    roles: ['partner_manager'] },
  { href: '/users',      label: 'المستخدمون',           roles: ['partner_manager'] },
  { href: '/audit',      label: 'سجل التدقيق',          roles: ['partner_manager'] },
  { href: '/settings',   label: 'الإعدادات',            roles: ['partner_manager'] },
]

export default function AppNav() {
  const { user } = useUser()
  const pathname = usePathname()
  const router = useRouter()

  if (!user) return null

  const items = NAV.filter((n) => n.roles.includes(user.role))

  return (
    <aside className="flex w-60 shrink-0 flex-col border-l border-gray-200 bg-white">
      <div className="border-b border-gray-200 px-4 py-3">
        <p className="font-semibold">{user.full_name}</p>
        <p className="text-xs text-gray-500">{ROLE_LABELS[user.role]}</p>
      </div>
      <nav className="flex-1 overflow-y-auto py-2">
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`block px-4 py-2 text-sm hover:bg-gray-50 ${
              pathname?.startsWith(item.href) ? 'bg-blue-50 font-semibold text-blue-800' : ''
            }`}
          >
            {item.label}
          </Link>
        ))}
      </nav>
      <button
        onClick={async () => {
          await signOut()
          router.replace('/login')
        }}
        className="border-t border-gray-200 px-4 py-3 text-right text-sm text-red-700 hover:bg-red-50"
      >
        تسجيل الخروج
      </button>
    </aside>
  )
}
