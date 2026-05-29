import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryBoundary } from '../QueryBoundary'
import type { QueryState } from '../../lib/api'

describe('QueryBoundary', () => {
  it('renders the default spinner while loading', () => {
    const state: QueryState<{ name: string }> = { kind: 'loading' }
    render(<QueryBoundary state={state}>{(d: { name: string }) => <span>{d.name}</span>}</QueryBoundary>)
    expect(screen.getByRole('status')).toBeTruthy()
  })

  it('renders the provided error slot on error', () => {
    const state: QueryState<{ name: string }> = { kind: 'error', error: new Error('x') }
    render(
      <QueryBoundary state={state} error={<span>boom</span>}>
        {(d: { name: string }) => <span>{d.name}</span>}
      </QueryBoundary>,
    )
    expect(screen.getByText('boom')).toBeTruthy()
  })

  it('renders the default error state when no error slot is provided', () => {
    const state: QueryState<{ name: string }> = { kind: 'error', error: new Error('x') }
    render(<QueryBoundary state={state}>{(d: { name: string }) => <span>{d.name}</span>}</QueryBoundary>)
    expect(screen.getByText("Couldn't load this page")).toBeTruthy()
  })

  it('renders children with data when ready', () => {
    const state: QueryState<{ name: string }> = { kind: 'ready', data: { name: 'alpha' } }
    render(<QueryBoundary state={state}>{(d: { name: string }) => <span>{d.name}</span>}</QueryBoundary>)
    expect(screen.getByText('alpha')).toBeTruthy()
  })
})
