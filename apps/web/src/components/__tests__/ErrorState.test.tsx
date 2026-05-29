import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ErrorState } from '../ErrorState'

describe('ErrorState', () => {
  it('renders title, helper, error tone and a default icon', () => {
    const { container } = render(
      <ErrorState title="Couldn't load X" helper="Try again" />,
    )
    expect(screen.getByText("Couldn't load X")).toBeTruthy()
    expect(screen.getByText('Try again')).toBeTruthy()
    expect(container.querySelector('.bg-red-100')).toBeTruthy()
    expect(container.querySelector('svg')).toBeTruthy()
  })

  it('uses a provided icon when given', () => {
    const { getByTestId } = render(
      <ErrorState title="t" helper="h" icon={<svg data-testid="custom" />} />,
    )
    expect(getByTestId('custom')).toBeTruthy()
  })
})
