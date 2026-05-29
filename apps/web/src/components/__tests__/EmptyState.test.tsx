import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EmptyState } from '../EmptyState'

describe('EmptyState', () => {
  it('renders icon, title and helper with muted tone', () => {
    const { container } = render(
      <EmptyState icon={<svg data-testid="icon" />} title="No items" helper="Add one" />,
    )
    expect(screen.getByText('No items')).toBeTruthy()
    expect(screen.getByText('Add one')).toBeTruthy()
    expect(screen.getByTestId('icon')).toBeTruthy()
    expect(container.querySelector('.bg-surface-muted')).toBeTruthy()
  })
})
