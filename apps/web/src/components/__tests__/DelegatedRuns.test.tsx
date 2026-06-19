import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { DelegatedRuns } from '../DelegatedRuns'
import type { DelegatedRun } from '../../lib/api/types'

const runs: DelegatedRun[] = [
  { run_id: 'run-4', harness: 'codex', model: 'gpt-5-codex', status: 'running', result: null, error: null, started_at: '2024-01-15T10:00:00.000Z' },
  { run_id: 'run-2', harness: 'cursor', model: 'auto', status: 'failed', result: null, error: { stderr_tail: 'boom' }, started_at: '2024-01-15T09:40:00.000Z' },
  { run_id: 'run-3', harness: 'claude-code', model: 'opus-4.8', status: 'completed', result: 'Refactored auth module; tests pass.', error: null, started_at: '2024-01-15T09:55:00.000Z' },
]

afterEach(cleanup)

describe('DelegatedRuns', () => {
  it('shows a quiet empty state when there are no runs', () => {
    render(<DelegatedRuns devcontainerId="dc-seed-0001" runs={[]} onChange={() => {}} />)
    expect(screen.getByText(/No delegated runs/i)).toBeTruthy()
  })

  it('renders a row per run with its status', () => {
    render(<DelegatedRuns devcontainerId="dc-seed-0001" runs={runs} onChange={() => {}} />)
    expect(screen.getByText('run-4')).toBeTruthy()
    expect(screen.getByText('running')).toBeTruthy()
    expect(screen.getByText('failed')).toBeTruthy()
  })

  it('offers Stop only on running rows', () => {
    render(<DelegatedRuns devcontainerId="dc-seed-0001" runs={runs} onChange={() => {}} />)
    expect(screen.getByTitle('Stop run-4')).toBeTruthy()
    expect(screen.queryByTitle('Stop run-2')).toBeNull()
  })

  it('does not show result/error inline', () => {
    render(<DelegatedRuns devcontainerId="dc-seed-0001" runs={runs} onChange={() => {}} />)
    expect(screen.queryByText('Refactored auth module; tests pass.')).toBeNull()
  })

  it('opens a dialog with the result when a completed run is clicked', () => {
    render(<DelegatedRuns devcontainerId="dc-seed-0001" runs={runs} onChange={() => {}} />)
    fireEvent.click(screen.getByText('run-3'))
    const dialog = screen.getByRole('dialog')
    expect(dialog).toBeTruthy()
    expect(screen.getByText('Refactored auth module; tests pass.')).toBeTruthy()
  })

  it('opens a dialog with the error when a failed run is clicked', () => {
    render(<DelegatedRuns devcontainerId="dc-seed-0001" runs={runs} onChange={() => {}} />)
    fireEvent.click(screen.getByText('run-2'))
    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(screen.getByText('boom')).toBeTruthy()
  })
})
