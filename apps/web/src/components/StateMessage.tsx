import type { ReactNode } from 'react'
import { cn } from '../lib/cn'

interface StateMessageProps {
  icon: ReactNode
  title: string
  helper: string
  tone?: 'muted' | 'error'
}

const TONE_CHIP: Record<'muted' | 'error', string> = {
  muted: 'bg-surface-muted text-accent',
  error: 'bg-red-100 text-bad',
}

export function StateMessage({ icon, title, helper, tone = 'muted' }: StateMessageProps) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="max-w-[320px] text-center">
        <div
          aria-hidden="true"
          className={cn(
            'mx-auto mb-3.5 flex h-10 w-10 items-center justify-center rounded-[10px]',
            TONE_CHIP[tone],
          )}
        >
          {icon}
        </div>
        <h2 className="mb-1.5 text-[15px] font-semibold text-text">{title}</h2>
        <p className="text-[13px] text-text-muted">{helper}</p>
      </div>
    </div>
  )
}
