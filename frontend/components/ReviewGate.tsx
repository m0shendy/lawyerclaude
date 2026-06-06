'use client'

// <ReviewGate/> — wraps any export/print/attach/send affordance. [C-II]
// Children are disabled (with an explanatory notice) unless review_state ===
// 'approved'. UX layer only — the backend rejects non-approved exports too.

import type { AiOutput } from '@/lib/types'
import type { ReactNode } from 'react'

export default function ReviewGate({
  output,
  children,
}: {
  output: AiOutput
  children: ReactNode
}) {
  const approved = output.review_state === 'approved'

  if (approved) return <>{children}</>

  return (
    <div className="relative inline-block" title="معطَّل حتى تتم المراجعة والاعتماد">
      <div className="pointer-events-none select-none opacity-40" aria-disabled>
        {children}
      </div>
      <p className="mt-1 text-xs text-red-700">
        التصدير / الإرسال معطَّل — يتطلب «تمت المراجعة والاعتماد» من المحامي المكلَّف أو الشريك.
      </p>
    </div>
  )
}
