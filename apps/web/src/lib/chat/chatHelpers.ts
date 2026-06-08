import type { LiveState } from '../stream/mergeTurns'

/**
 * Returns true when the scroll container should stay pinned to the bottom.
 * "At bottom" = distance from bottom is within `threshold` pixels (default 40).
 * When all dimensions are 0 (happy-dom / no layout) the result is true (stick).
 */
export function shouldStick(
  scrollTop: number,
  scrollHeight: number,
  clientHeight: number,
  threshold = 40,
): boolean {
  return scrollHeight - scrollTop - clientHeight <= threshold
}

/** True when any live turn has a non-empty text block currently streaming. */
export function hasLiveText(live: LiveState): boolean {
  return live.order.some((id) =>
    live.byId[id]?.some((b) => b.kind === 'text' && b.text.length > 0),
  )
}

/**
 * True when the working/typing indicator should be shown:
 * session is active, run has not ended, and no live text is streaming yet.
 * Covers the "agent thinking or running a tool" gap.
 */
export function isWorkingIndicatorVisible(isActive: boolean, live: LiveState): boolean {
  return isActive && !live.ended && !hasLiveText(live)
}
