import { createBrowserRouter, redirect } from 'react-router'
import { AppShell } from './AppShell'
import { Devcontainers } from './Devcontainers'
import { DevcontainerDetail } from './DevcontainerDetail'
import { Inbox } from './Inbox'
import { Approvals } from './Approvals'
import { Settings } from './Settings'

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
      { path: '*', loader: () => redirect('/devcontainers') },
    ],
  },
])
