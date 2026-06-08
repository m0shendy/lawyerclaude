'use client'

// Portal documents — shared files visible to the client.
// GET /portal/documents — returns all portal_visible docs on the client's cases.
// Files are served via Supabase Storage public/signed URL.

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
const STORAGE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL
  ? `${process.env.NEXT_PUBLIC_SUPABASE_URL}/storage/v1/object/public/documents`
  : null

interface PortalDocument {
  id: string
  case_id: string
  file_name: string
  file_path: string
  created_at: string
}

async function portalGet<T>(path: string, token: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? 'خطأ')
  return res.json() as Promise<T>
}

function fileIcon(name: string) {
  const ext = name.split('.').pop()?.toLowerCase()
  if (['pdf'].includes(ext ?? '')) return '📄'
  if (['doc', 'docx'].includes(ext ?? '')) return '📝'
  if (['xls', 'xlsx'].includes(ext ?? '')) return '📊'
  if (['jpg', 'jpeg', 'png'].includes(ext ?? '')) return '🖼'
  return '📎'
}

export default function PortalDocumentsPage() {
  const router = useRouter()
  const [docs, setDocs] = useState<PortalDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const token = sessionStorage.getItem('portal_token')
    if (!token) { router.replace('/portal/login'); return }

    portalGet<PortalDocument[]>('/portal/documents', token)
      .then(setDocs)
      .catch(e => {
        if (e.message?.includes('401')) {
          sessionStorage.removeItem('portal_token')
          router.replace('/portal/login')
        } else {
          setError(e.message ?? 'حدث خطأ')
        }
      })
      .finally(() => setLoading(false))
  }, [])

  function downloadUrl(filePath: string) {
    if (STORAGE_URL) return `${STORAGE_URL}/${filePath}`
    // Fallback: backend proxy (would need a /portal/documents/{id}/download endpoint)
    return null
  }

  return (
    <div className="min-h-screen bg-gray-50" dir="rtl">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white px-4 py-4">
        <div className="mx-auto max-w-3xl flex items-center justify-between">
          <h1 className="text-lg font-bold">مستنداتي</h1>
          <Link href="/portal/dashboard" className="text-sm text-gray-500 hover:text-gray-700">
            ← الرئيسية
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-6">
        {error && (
          <div className="mb-4 rounded bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>
        )}

        {loading ? (
          <p className="text-sm text-gray-500">جارٍ التحميل…</p>
        ) : docs.length === 0 ? (
          <div className="rounded-xl border border-gray-200 bg-white px-6 py-10 text-center shadow-sm">
            <p className="text-gray-500 text-sm">لا توجد مستندات مشاركة معك حتى الآن</p>
            <p className="text-gray-400 text-xs mt-1">سيتوفر المستند هنا فور مشاركته من قبل مكتب المحاماة</p>
          </div>
        ) : (
          <div className="space-y-2">
            {docs.map(doc => {
              const url = downloadUrl(doc.file_path)
              const date = new Date(doc.created_at).toLocaleDateString('ar-EG', {
                year: 'numeric', month: 'long', day: 'numeric',
              })
              return (
                <div
                  key={doc.id}
                  className="flex items-center justify-between rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="text-2xl shrink-0" aria-hidden>{fileIcon(doc.file_name)}</span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-gray-900">{doc.file_name}</p>
                      <p className="text-xs text-gray-400">{date}</p>
                    </div>
                  </div>
                  {url ? (
                    <a
                      href={url}
                      download={doc.file_name}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="shrink-0 rounded-lg bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-100"
                    >
                      تحميل
                    </a>
                  ) : (
                    <span className="shrink-0 text-xs text-gray-400">غير متاح</span>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </main>

      {/* Bottom nav */}
      <nav className="fixed bottom-0 inset-x-0 border-t border-gray-200 bg-white px-4 py-2">
        <div className="mx-auto flex max-w-3xl justify-around">
          <Link href="/portal/dashboard" className="flex flex-col items-center gap-0.5 text-xs text-gray-500 hover:text-blue-700">
            <span>🏠</span>الرئيسية
          </Link>
          <Link href="/portal/documents" className="flex flex-col items-center gap-0.5 text-xs text-blue-700 font-medium">
            <span>📁</span>المستندات
          </Link>
        </div>
      </nav>
      <div className="h-16" />
    </div>
  )
}
