import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LoadingState } from '../LoadingState'

describe('LoadingState', () => {
  it('renders a status spinner', () => {
    render(<LoadingState />)
    expect(screen.getByRole('status')).toBeTruthy()
  })

  it('renders an optional label', () => {
    render(<LoadingState label="Loading devcontainers…" />)
    expect(screen.getByText('Loading devcontainers…')).toBeTruthy()
  })
})
