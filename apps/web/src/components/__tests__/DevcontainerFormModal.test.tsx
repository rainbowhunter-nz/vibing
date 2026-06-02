import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DevcontainerFormModal } from '../DevcontainerFormModal'
import { createDevcontainer, updateDevcontainer } from '../../lib/api'
import type { Devcontainer } from '../../lib/api/types'

vi.mock('../../lib/api/endpoints')
const mockCreate = vi.mocked(createDevcontainer)
const mockUpdate = vi.mocked(updateDevcontainer)

const existing: Devcontainer = {
  id: 'dc1',
  name: 'api-service',
  local_path: '/home/me/projects/api',
  status: 'stopped',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => cleanup())

describe('DevcontainerFormModal — create', () => {
  it('submits name and local_path', async () => {
    mockCreate.mockResolvedValue(existing)
    const onSuccess = vi.fn()
    render(<DevcontainerFormModal mode="create" onClose={vi.fn()} onSuccess={onSuccess} />)

    await userEvent.type(screen.getByLabelText('Name'), 'api-service')
    await userEvent.type(screen.getByLabelText('Local path'), '/home/me/projects/api')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))

    expect(mockCreate).toHaveBeenCalledWith({ name: 'api-service', local_path: '/home/me/projects/api' })
    expect(onSuccess).toHaveBeenCalled()
  })

  it('disables submit until both fields are filled', async () => {
    render(<DevcontainerFormModal mode="create" onClose={vi.fn()} onSuccess={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Create' }).hasAttribute('disabled')).toBe(true)

    await userEvent.type(screen.getByLabelText('Name'), 'x')
    await userEvent.type(screen.getByLabelText('Local path'), '/p')
    expect(screen.getByRole('button', { name: 'Create' }).hasAttribute('disabled')).toBe(false)
  })

  it('shows the backend error message and keeps input on failure', async () => {
    mockCreate.mockRejectedValue(new Error('path does not exist'))
    render(<DevcontainerFormModal mode="create" onClose={vi.fn()} onSuccess={vi.fn()} />)

    await userEvent.type(screen.getByLabelText('Name'), 'api-service')
    await userEvent.type(screen.getByLabelText('Local path'), '/bad')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))

    await screen.findByText('path does not exist')
    expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('api-service')
  })

  it('calls onClose on Cancel and on Escape', async () => {
    const onClose = vi.fn()
    render(<DevcontainerFormModal mode="create" onClose={onClose} onSuccess={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})

describe('DevcontainerFormModal — edit', () => {
  it('prefills name and renders local path read-only', () => {
    render(<DevcontainerFormModal mode="edit" devcontainer={existing} onClose={vi.fn()} onSuccess={vi.fn()} />)
    expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('api-service')
    const path = screen.getByLabelText('Local path') as HTMLInputElement
    expect(path.value).toBe('/home/me/projects/api')
    expect(path.readOnly).toBe(true)
  })

  it('submits only the name via updateDevcontainer', async () => {
    mockUpdate.mockResolvedValue({ ...existing, name: 'renamed' })
    const onSuccess = vi.fn()
    render(<DevcontainerFormModal mode="edit" devcontainer={existing} onClose={vi.fn()} onSuccess={onSuccess} />)

    const nameInput = screen.getByLabelText('Name')
    await userEvent.clear(nameInput)
    await userEvent.type(nameInput, 'renamed')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(mockUpdate).toHaveBeenCalledWith('dc1', { name: 'renamed' })
    expect(onSuccess).toHaveBeenCalled()
  })
})
