'use client'

import type { ReactNode } from 'react'
import { UserProvider } from '@/lib/rbac'

export default function Providers({ children }: { children: ReactNode }) {
  return <UserProvider>{children}</UserProvider>
}
