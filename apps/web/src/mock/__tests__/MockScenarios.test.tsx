import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { resetScenario, getScenario } from '../scenario'
import { MockScenarios } from '../../routes/MockScenarios'
import { RailMock } from '../RailMock'
import { SCENARIOS } from '../scenario'

beforeEach(() => {
  act(() => resetScenario())
})

afterEach(() => {
  cleanup()
})

function renderScenarios() {
  return render(
    <MemoryRouter>
      <MockScenarios />
    </MemoryRouter>,
  )
}

describe('MockScenarios route', () => {
  it('renders all 6 scenario buttons', () => {
    renderScenarios()
    for (const s of SCENARIOS) {
      expect(screen.getByRole('button', { name: new RegExp(s) })).toBeTruthy()
    }
  })

  it('shows "happy" as active by default', () => {
    renderScenarios()
    const btn = screen.getByRole('button', { name: /happy/ })
    expect(btn.getAttribute('aria-pressed')).toBe('true')
  })

  it('switches active scenario when a button is clicked', async () => {
    const user = userEvent.setup()
    renderScenarios()
    await user.click(screen.getByRole('button', { name: /api-error/ }))
    expect(getScenario()).toBe('api-error')
    expect(screen.getByRole('button', { name: /api-error/ }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByRole('button', { name: /happy/ }).getAttribute('aria-pressed')).toBe('false')
  })

  it('updates active label when scenario changes', async () => {
    const user = userEvent.setup()
    renderScenarios()
    await user.click(screen.getByRole('button', { name: /empty/ }))
    // "active" label text appears next to the active scenario button
    expect(screen.getAllByText(/active/).length).toBeGreaterThan(0)
  })
})

describe('RailMock component', () => {
  it('shows the active scenario name', () => {
    render(
      <MemoryRouter>
        <RailMock />
      </MemoryRouter>,
    )
    expect(screen.getByText('happy')).toBeTruthy()
  })

  it('updates when scenario changes', async () => {
    const user = userEvent.setup()

    // Render both components so a click on the scenarios page updates the rail
    const { container } = render(
      <MemoryRouter>
        <RailMock />
        <MockScenarios />
      </MemoryRouter>,
    )

    // RailMock renders the active scenario name inside the <section> heading area
    const section = container.querySelector('section')!
    expect(section.textContent).toContain('happy')
    await user.click(screen.getByRole('button', { name: /^empty/ }))
    expect(section.textContent).toContain('empty')
  })

  it('has a link to /mock', () => {
    render(
      <MemoryRouter>
        <RailMock />
      </MemoryRouter>,
    )
    const link = screen.getByRole('link', { name: /switch scenario/i })
    expect(link).toBeTruthy()
  })
})
