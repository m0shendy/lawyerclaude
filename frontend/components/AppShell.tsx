'use client'

// Authenticated screen wrapper: sidebar nav + content area.
// Use on every screen except /login.

import type { ReactNode } from 'react'
import AppNav from './AppNav'

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <AppNav />
      <main className="flex-1 overflow-x-auto p-6">{children}</main>
    </div>
  )
}
