import { createBrowserRouter, redirect } from 'react-router'
import { AppShell } from './AppShell'
import { Workspaces } from './Workspaces'
import { WorkspaceDetail } from './WorkspaceDetail'
import { Inbox } from './Inbox'
import { Approvals } from './Approvals'
import { Settings } from './Settings'

export const router = createBrowserRouter([
  {
    path: '/',
    Component: AppShell,
    children: [
      { index: true, loader: () => redirect('/workspaces') },
      { path: 'workspaces', Component: Workspaces },
      { path: 'workspaces/:id', Component: WorkspaceDetail },
      { path: 'inbox', Component: Inbox },
      { path: 'approvals', Component: Approvals },
      { path: 'settings', Component: Settings },
      { path: '*', loader: () => redirect('/workspaces') },
    ],
  },
])
