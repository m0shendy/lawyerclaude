import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import './globals.css'
import Disclaimer from '@/components/Disclaimer'
import Providers from './providers'

// App shell (T028): RTL Arabic layout + persistent assistive-tool disclaimer
// on every screen. [C-VIII]

export const metadata: Metadata = {
  title: 'نظام إدارة مكتب المحاماة',
  description: 'نظام إدارة مكاتب المحاماة بمساعدة الذكاء الاصطناعي — أداة مساعدة، ليست استشارة قانونية',
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ar" dir="rtl">
      <body className="min-h-screen bg-gray-50 pb-8 text-gray-900">
        <Providers>{children}</Providers>
        <Disclaimer />
      </body>
    </html>
  )
}
