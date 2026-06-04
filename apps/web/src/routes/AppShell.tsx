import { Outlet } from 'react-router'
import { Sidebar } from '../components/Sidebar'
import { RailActivity } from '../components/RailActivity'
import { RailBackend } from '../components/RailBackend'
import { isMockMode } from '../mock'
import { RailMock } from '../mock/RailMock'

export function AppShell() {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar />
      <main className="flex flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>
      <aside aria-label="Activity" className="flex w-[240px] flex-col gap-4 border-l border-border bg-surface-rail p-4">
        <RailActivity />
        <div className="flex-1" />
        {isMockMode() && <RailMock />}
        <RailBackend />
      </aside>
    </div>
  )
}
