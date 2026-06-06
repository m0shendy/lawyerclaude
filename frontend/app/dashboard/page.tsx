'use client'

// T040 — Dashboard (all roles, role-aware) per contracts/ui-screens.md.
// Lean first version: welcome header, assigned-cases card from /me, quick
// links grid, manager-only admin links row. Deadline/task/review summaries
// arrive in later phases (no aggregation endpoints yet) — shown as "قريباً".

import Link from 'next/link'
import AppShell from '@/components/AppShell'
import { ALL_ROLES, MANAGER_ONLY, RequireRole, useUser } from '@/lib/rbac'
import { ROLE_LABELS, type Case, type Role } from '@/lib/types'

interface QuickLink {
  href: string
  label: string
  description: string
  roles: Role[]
}

const QUICK_LINKS: QuickLink[] = [
  { href: '/cases', label: 'القضايا', description: 'استعراض القضايا وإدارتها', roles: ALL_ROLES },
  { href: '/documents', label: 'المستندات', description: 'رفع المستندات ومتابعة حالتها', roles: ALL_ROLES },
  { href: '/deadlines', label: 'المواعيد والالتزامات', description: 'متابعة المواعيد القادمة', roles: ALL_ROLES },
  {
    href: '/tasks',
    label: 'المهام',
    description: 'إدارة مهام اليوم ومتابعتها',
    roles: ['partner_manager', 'lawyer', 'paralegal'],
  },
  {
    href: '/ai-review',
    label: 'مراجعة الذكاء الاصطناعي',
    description: 'مراجعة واعتماد المخرجات المولّدة',
    roles: ALL_ROLES,
  },
]

const MANAGER_LINKS: QuickLink[] = [
  { href: '/users', label: 'المستخدمون', description: 'إدارة المستخدمين والأدوار', roles: MANAGER_ONLY },
  { href: '/audit', label: 'سجل التدقيق', description: 'سجل التغييرات للقراءة فقط', roles: MANAGER_ONLY },
  { href: '/reports', label: 'التقارير', description: 'التقارير اليومية للمكتب', roles: MANAGER_ONLY },
  { href: '/settings', label: 'الإعدادات', description: 'إعدادات المكتب والمفاتيح', roles: MANAGER_ONLY },
]

// Placeholder summary cards until dedicated aggregation endpoints exist.
const PLACEHOLDER_CARDS: { title: string }[] = [
  { title: 'المواعيد القادمة' },
  { title: 'مهام اليوم' },
  { title: 'عناصر بانتظار المراجعة' },
]

function AssignedCasesCard({ cases }: { cases: Case[] }) {
  const latest = [...cases]
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    .slice(0, 5)

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-bold">القضايا المسندة إليّ</h2>
        <span className="rounded-full bg-blue-50 px-3 py-1 text-sm font-semibold text-blue-800">
          {cases.length}
        </span>
      </div>

      {latest.length === 0 ? (
        <p className="text-sm text-gray-500">لا توجد قضايا مسندة إليك حالياً.</p>
      ) : (
        <ul className="divide-y divide-gray-100">
          {latest.map((c) => (
            <li key={c.id}>
              <Link
                href={`/cases/${c.id}`}
                className="block rounded px-2 py-2 hover:bg-gray-50"
              >
                <p className="text-sm font-semibold">{c.title}</p>
                <p className="text-xs text-gray-500">
                  {c.client_name}
                  {c.case_number ? <span dir="ltr"> · {c.case_number}</span> : null}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <Link
        href="/cases"
        className="mt-3 inline-block text-sm font-semibold text-blue-700 hover:underline"
      >
        عرض كل القضايا ←
      </Link>
    </section>
  )
}

function PlaceholderCard({ title }: { title: string }) {
  return (
    <section className="rounded-xl border border-dashed border-gray-300 bg-white p-5">
      <h2 className="mb-2 font-bold">{title}</h2>
      <p className="text-sm text-gray-400">قريباً</p>
    </section>
  )
}

function LinksGrid({ links }: { links: QuickLink[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {links.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition hover:border-blue-300 hover:bg-blue-50"
        >
          <p className="font-semibold text-blue-800">{l.label}</p>
          <p className="mt-1 text-xs text-gray-500">{l.description}</p>
        </Link>
      ))}
    </div>
  )
}

function DashboardContent() {
  const { user } = useUser()
  if (!user) return null // RequireRole already handles loading/redirect

  const quickLinks = QUICK_LINKS.filter((l) => l.roles.includes(user.role))
  const isManager = user.role === 'partner_manager'

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">مرحباً، {user.full_name}</h1>
        <p className="mt-1 text-sm text-gray-500">{ROLE_LABELS[user.role]}</p>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <AssignedCasesCard cases={user.assigned_cases} />
        <div className="grid grid-cols-1 gap-4">
          {PLACEHOLDER_CARDS.map((c) => (
            <PlaceholderCard key={c.title} title={c.title} />
          ))}
        </div>
      </div>

      <section>
        <h2 className="mb-3 font-bold">روابط سريعة</h2>
        <LinksGrid links={quickLinks} />
      </section>

      {isManager && (
        <section>
          <h2 className="mb-3 font-bold">إدارة المكتب</h2>
          <LinksGrid links={MANAGER_LINKS} />
        </section>
      )}
    </div>
  )
}

export default function DashboardPage() {
  return (
    <RequireRole roles={ALL_ROLES}>
      <AppShell>
        <DashboardContent />
      </AppShell>
    </RequireRole>
  )
}
