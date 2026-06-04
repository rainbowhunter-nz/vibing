import { cn } from '../cn'

export function ActionButton({
  label,
  onClick,
  disabled,
  variant,
}: {
  label: string
  onClick: () => void
  disabled: boolean
  variant: 'approve' | 'reject'
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'rounded-md px-3 py-1 text-[12px] font-semibold disabled:opacity-40',
        variant === 'approve' ? 'bg-ok text-white' : 'border border-bad text-bad',
      )}
    >
      {label}
    </button>
  )
}
