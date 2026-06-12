'use client'

// T027 — frontend RBAC guards. [C-I]
// UX-layer only: the server enforces RBAC on every endpoint regardless.

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { apiGet } from './api'
import { getSession } from './supabase'
import type { Me, Role } from './types'

interface UserContextValue {
  user: Me | null
  loading: boolean
  refresh: () => Promise<Me | null>
}

const UserContext = createContext<UserContextValue>({
  user: null,
  loading: true,
  refresh: async () => null,
})

export function UserProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = async () => {
    try {
      const session = await getSession()
      if (!session) {
        setUser(null)
        return null
      }
      const me = await apiGet<Me>('/me')
      setUser(me)
      return me
    } catch (e) {
      setUser(null)
      throw e
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh().catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return <UserContext.Provider value={{ user, loading, refresh }}>{children}</UserContext.Provider>
}

export function useUser(): UserContextValue {
  return useContext(UserContext)
}

/** Client guard: renders children only when the user holds one of `roles`.
 *  Unauthenticated → /login; unauthorized → /dashboard. */
export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user, loading } = useUser()
  const router = useRouter()

  useEffect(() => {
    if (loading) return
    if (!user) {
      router.replace('/login')
    } else if (!roles.includes(user.role)) {
      router.replace('/dashboard')
    }
  }, [user, loading, roles, router])

  if (loading) {
    return <div className="p-8 text-center text-gray-500">جارٍ التحميل…</div>
  }
  if (!user || !roles.includes(user.role)) return null
  return <>{children}</>
}

export const ALL_ROLES: Role[] = ['partner_manager', 'lawyer', 'paralegal', 'secretary']
export const MANAGER_ONLY: Role[] = ['partner_manager']
