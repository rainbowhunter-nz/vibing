const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 60 * 60 * 24 * 365],
  ['month', 60 * 60 * 24 * 30],
  ['day', 60 * 60 * 24],
  ['hour', 60 * 60],
  ['minute', 60],
  ['second', 1],
]

const relativeTimeFormat = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

export function formatRelativeTime(iso: string): string {
  const seconds = Math.round((new Date(iso).getTime() - Date.now()) / 1000)
  const abs = Math.abs(seconds)
  for (const [unit, secondsPerUnit] of RELATIVE_UNITS) {
    if (abs >= secondsPerUnit || unit === 'second') {
      return relativeTimeFormat.format(Math.round(seconds / secondsPerUnit), unit)
    }
  }
  return relativeTimeFormat.format(0, 'second')
}
