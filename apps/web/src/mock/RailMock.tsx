import { NavLink } from 'react-router'
import { cn } from '../lib/cn'
import { useScenario } from './useScenario'

export function RailMock() {
  const [active] = useScenario()

  return (
    <section>
      <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">
        Mock
      </h3>
      <div className="mb-1.5 flex items-center gap-2 text-[12px] text-text-muted">
        <span className="h-2 w-2 rounded-full bg-accent" />
        {active}
      </div>
      <NavLink
        to="/mock"
        className={({ isActive }) =>
          cn(
            'ml-4 text-[11px] text-text-subtle underline-offset-2 hover:underline',
            isActive && 'font-medium text-text',
          )
        }
      >
        switch scenario
      </NavLink>
    </section>
  )
}
