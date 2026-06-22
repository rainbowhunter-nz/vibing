import { render, screen, cleanup } from '@testing-library/react'
import { describe, expect, it, afterEach } from 'vitest'
import { LifecycleHeader } from './DevcontainerDetail'

afterEach(cleanup)

const base = {
  id: 'dc-1', name: 'demo', local_path: '/x', status: 'running' as const,
  source: 'manual' as const, created_at: null, updated_at: null,
  runtime: { runtime_connected: true },
}

describe('LifecycleHeader actions', () => {
  it('shows Stop and Remove container when running, without runtime controls', () => {
    render(<LifecycleHeader dc={base} busy={false} onAction={() => {}} />)
    expect(screen.getByTitle('Stop')).toBeTruthy()
    expect(screen.getByTitle('Remove container')).toBeTruthy()
    expect(screen.queryByTitle('Inject runtime')).toBeNull()
    expect(screen.queryByText('Connected')).toBeNull()
  })

  it('shows Start when stopped', () => {
    render(<LifecycleHeader dc={{ ...base, status: 'stopped' }} busy={false} onAction={() => {}} />)
    expect(screen.getByTitle('Start')).toBeTruthy()
  })

  it('Start is disabled when status is starting', () => {
    render(<LifecycleHeader dc={{ ...base, status: 'starting' }} busy={false} onAction={() => {}} />)
    expect((screen.getByTitle('Start') as HTMLButtonElement).disabled).toBeTruthy()
  })
})
