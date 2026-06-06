'use client'

// <AiMarkedOutput/> — every AI-generated output renders through this. [C-II][C-V][C-VI]
//  * banner "AI-generated — requires review" until approved  [C-VI]
//  * per-claim source links → document chunks                 [C-V]
//  * heightened red warning when low_confidence_flag           [C-VII]

import Link from 'next/link'
import type { AiOutput, SourceLink } from '@/lib/types'
import type { ReactNode } from 'react'

function SourceLinks({ links }: { links: SourceLink[] }) {
  if (!links.length) return null
  return (
    <div className="mt-2 flex flex-wrap gap-2 text-xs">
      <span className="text-gray-500">المصادر:</span>
      {links.map((l, i) => (
        <Link
          key={`${l.chunk_id}-${i}`}
          href={`/documents/${l.document_id}?chunk=${l.chunk_id}`}
          className="rounded bg-blue-50 px-2 py-0.5 text-blue-700 hover:bg-blue-100"
        >
          {l.page_ref != null ? `صفحة ${l.page_ref}` : `مقطع ${i + 1}`}
        </Link>
      ))}
    </div>
  )
}

export default function AiMarkedOutput({
  output,
  children,
}: {
  output: AiOutput
  children?: ReactNode
}) {
  const approved = output.review_state === 'approved'

  return (
    <div className="rounded-lg border border-gray-200 bg-white">
      {!approved && (
        <div className="flex items-center gap-2 rounded-t-lg bg-violet-100 px-3 py-2 text-sm font-semibold text-violet-900">
          <span aria-hidden>🤖</span>
          محتوى مولَّد بالذكاء الاصطناعي — يتطلب المراجعة
        </div>
      )}
      {approved && (
        <div className="flex items-center gap-2 rounded-t-lg bg-green-50 px-3 py-1.5 text-xs text-green-800">
          ✓ تمت المراجعة والاعتماد
          {output.approved_at && (
            <span className="text-green-600">
              ({new Date(output.approved_at).toLocaleDateString('ar-EG')})
            </span>
          )}
        </div>
      )}

      {output.low_confidence_flag && (
        <div className="border-y border-red-300 bg-red-50 px-3 py-2 text-sm font-semibold text-red-800">
          ⚠ تحذير مشدَّد: هذا المحتوى مستخرج من مستند بجودة مسح منخفضة — راجع الأصل بعناية
          مضاعفة قبل أي اعتماد.
        </div>
      )}

      <div className="p-4">
        {children}
        <SourceLinks links={output.source_links} />
      </div>
    </div>
  )
}
