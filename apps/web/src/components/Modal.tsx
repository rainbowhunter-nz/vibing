import { useEffect, type ReactNode } from 'react'
import { cn } from '../lib/cn'

export function Modal({ ariaLabel, header, children, onClose, className }: {
  ariaLabel: string
  header: ReactNode
  children: ReactNode
  onClose: () => void
  className?: string
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel}
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 pt-24"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={cn('flex max-h-[70vh] w-[480px] flex-col overflow-hidden rounded-[10px] border border-border bg-bg shadow-xl', className)}
      >
        <div className="flex items-center gap-2 border-b border-border px-4 py-3.5">
          {header}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="ml-auto text-text-muted hover:text-text"
          >
            ✕
          </button>
        </div>
        <div className="overflow-y-auto p-4">{children}</div>
      </div>
    </div>
  )
}
