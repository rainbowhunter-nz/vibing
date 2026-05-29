import { NavLink } from 'react-router'
import { cn } from '../lib/cn'

const ITEMS = [
  { to: '/devcontainers', label: 'Devcontainers' },
  { to: '/inbox', label: 'Inbox' },
  { to: '/approvals', label: 'Approvals' },
  { to: '/settings', label: 'Settings' },
] as const

export function Sidebar() {
  return (
    <aside aria-label="Primary" className="flex w-[200px] flex-col border-r border-border bg-surface-sidebar py-4">
      <div className="px-[18px] pb-[18px] text-[15px] font-semibold tracking-tight text-text">
        Vibing
      </div>
      <nav aria-label="Main" className="flex flex-col">
        {ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                'border-l-2 border-transparent px-[18px] py-2 text-[13px] text-text-muted',
                isActive && 'border-l-accent bg-accent-bg font-medium text-text',
              )
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
