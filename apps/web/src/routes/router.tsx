import { createBrowserRouter, redirect } from 'react-router'
import { AppShell } from './AppShell'
import { Devcontainers } from './Devcontainers'
import { DevcontainerDetail } from './DevcontainerDetail'
import { Inbox } from './Inbox'
import { Approvals } from './Approvals'
import { Settings } from './Settings'

const devOnlyRoutes = import.meta.env.VITE_API_MOCKING === 'true'
  ? [{ path: 'mock', lazy: () => import('./MockScenarios').then((m) => ({ Component: m.MockScenarios })) }]
  : []

export const router = createBrowserRouter([
  {
    path: '/',
    Component: AppShell,
    children: [
      { index: true, loader: () => redirect('/devcontainers') },
      { path: 'devcontainers', Component: Devcontainers },
      { path: 'devcontainers/:id', Component: DevcontainerDetail },
      { path: 'inbox', Component: Inbox },
      { path: 'approvals', Component: Approvals },
      { path: 'settings', Component: Settings },
      ...devOnlyRoutes,
      { path: '*', loader: () => redirect('/devcontainers') },
    ],
  },
])
