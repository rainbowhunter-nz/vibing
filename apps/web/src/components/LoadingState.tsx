interface LoadingStateProps {
  label?: string
}

export function LoadingState({ label }: LoadingStateProps) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8">
      <div
        role="status"
        aria-label="Loading"
        className="h-5 w-5 animate-spin rounded-full border-2 border-border border-t-accent"
      />
      {label && <p className="text-[13px] text-text-muted">{label}</p>}
    </div>
  )
}
