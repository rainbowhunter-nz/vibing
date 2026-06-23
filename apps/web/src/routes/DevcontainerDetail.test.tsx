import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { describe, expect, it, afterEach } from 'vitest'
import type { DevcontainerView } from '../lib/api/types'
import { LifecycleHeader, RuntimeSection } from './DevcontainerDetail'

afterEach(cleanup)

const base: DevcontainerView = {
  id: 'dc-1', name: 'demo', local_path: '/x', status: 'running',
  source: 'manual', created_at: null, updated_at: null,
  runtime: { state: 'connected' },
}

function renderDetail(dc: DevcontainerView) {
  return render(<RuntimeSection dc={dc} busy={false} onAction={() => {}} />)
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

describe('RuntimeSection', () => {
  it('shows Connected and a Stop runtime button when running and connected', () => {
    const calls: string[] = []
    render(<RuntimeSection dc={base} busy={false} onAction={(k) => calls.push(k)} />)
    expect(screen.getByText('Connected')).toBeTruthy()
    expect(screen.getByTitle('Stop runtime')).toBeTruthy()
  })

  it('shows Start the container to inject runtime when stopped and disconnected', () => {
    const calls: string[] = []
    const dc = { ...base, status: 'stopped' as const, runtime: { state: 'disconnected' as const } }
    render(<RuntimeSection dc={dc} busy={false} onAction={(k) => calls.push(k)} />)
    const inject = screen.getByTitle('Start the container to inject runtime') as HTMLButtonElement
    expect(inject.disabled).toBe(true)
    inject.click()
    expect(calls).toEqual([])
  })

  it('shows Launching when state is launching', () => {
    renderDetail({ ...base, runtime: { state: 'launching' as const } })
    expect(screen.getByText('Launching…')).toBeTruthy()
  })

  it('shows Disconnected when not connected', () => {
    renderDetail({ ...base, status: 'running' as const, runtime: { state: 'disconnected' as const } })
    expect(screen.getByText('Disconnected')).toBeTruthy()
  })

  it('opens the runtime logs dialog', async () => {
    renderDetail(base)
    fireEvent.click(screen.getByTitle('View runtime logs'))
    expect(await screen.findByText('Runtime logs')).toBeTruthy()
  })

  it('shows Error and a visible Inject button when state is error and running', () => {
    const calls: string[] = []
    const dc = { ...base, status: 'running' as const, runtime: { state: 'error' as const } }
    render(<RuntimeSection dc={dc} busy={false} onAction={(k) => calls.push(k)} />)
    expect(screen.getByText('Error')).toBeTruthy()
    const inject = screen.getByTitle('Inject runtime') as HTMLButtonElement
    expect(inject.disabled).toBe(false)
    inject.click()
    expect(calls).toEqual(['inject'])
  })
})
