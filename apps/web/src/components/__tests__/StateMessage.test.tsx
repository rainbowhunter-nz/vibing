import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StateMessage } from '../StateMessage'

describe('StateMessage', () => {
  it('renders title and helper', () => {
    render(<StateMessage icon={<svg />} title="Title here" helper="Helper here" />)
    expect(screen.getByText('Title here')).toBeTruthy()
    expect(screen.getByText('Helper here')).toBeTruthy()
  })

  it('uses muted chip by default and error chip when tone="error"', () => {
    const { container, rerender } = render(
      <StateMessage icon={<svg />} title="t" helper="h" />,
    )
    expect(container.querySelector('.bg-surface-muted')).toBeTruthy()
    rerender(<StateMessage icon={<svg />} title="t" helper="h" tone="error" />)
    expect(container.querySelector('.bg-red-100')).toBeTruthy()
  })
})
