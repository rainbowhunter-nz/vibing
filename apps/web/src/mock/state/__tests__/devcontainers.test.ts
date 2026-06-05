import { describe, it, expect, beforeEach } from 'vitest'
import {
  resetDevcontainers,
  listDevcontainers,
  getDevcontainer,
  createDevcontainer,
  updateDevcontainer,
  startDevcontainer,
  stopDevcontainer,
  deleteDevcontainer,
  NotFoundError,
} from '../devcontainers'

beforeEach(() => resetDevcontainers())

describe('listDevcontainers', () => {
  it('returns seeded items in happy state', () => {
    const { items } = listDevcontainers()
    expect(items.length).toBeGreaterThanOrEqual(4)
    expect(items.some((d) => d.status === 'running')).toBe(true)
    expect(items.some((d) => d.status === 'stopped')).toBe(true)
    expect(items.some((d) => d.status === 'created')).toBe(true)
    expect(items.some((d) => d.status === 'error')).toBe(true)
  })

  it('returns DevcontainerView shape (includes runtime)', () => {
    const { items } = listDevcontainers()
    for (const item of items) {
      expect(item).toHaveProperty('runtime')
      expect(item.runtime).toHaveProperty('worker_connected')
      expect(item.runtime).toHaveProperty('agent_connected')
    }
  })
})

describe('getDevcontainer', () => {
  it('returns DevcontainerView with runtime by seeded id', () => {
    const dc = getDevcontainer('dc-seed-0001')
    expect(dc.id).toBe('dc-seed-0001')
    expect(dc.name).toBe('my-webapp')
    expect(dc.runtime).toEqual({ worker_connected: true, agent_connected: true })
  })

  it('throws NotFoundError for unknown id', () => {
    expect(() => getDevcontainer('nonexistent')).toThrow(NotFoundError)
    expect(() => getDevcontainer('nonexistent')).toThrow(/nonexistent/)
    const err = (() => { try { getDevcontainer('x') } catch (e) { return e } })()
    expect((err as NotFoundError).code).toBe('DEVCONTAINER_NOT_FOUND')
  })
})

describe('createDevcontainer', () => {
  it('adds a new devcontainer to the list', () => {
    const before = listDevcontainers().items.length
    createDevcontainer({ name: 'new-one', local_path: '/home/dev/new-one' })
    expect(listDevcontainers().items.length).toBe(before + 1)
  })

  it('returns the created devcontainer with status "created"', () => {
    const dc = createDevcontainer({ name: 'fresh', local_path: '/tmp/fresh' })
    expect(dc.name).toBe('fresh')
    expect(dc.local_path).toBe('/tmp/fresh')
    expect(dc.status).toBe('created')
    expect(dc.id).toBeTruthy()
  })

  it('created item is fetchable by id', () => {
    const created = createDevcontainer({ name: 'fetchable', local_path: '/tmp/fetchable' })
    const fetched = getDevcontainer(created.id)
    expect(fetched.name).toBe('fetchable')
  })
})

describe('updateDevcontainer', () => {
  it('renames a devcontainer', () => {
    updateDevcontainer('dc-seed-0002', { name: 'renamed' })
    expect(getDevcontainer('dc-seed-0002').name).toBe('renamed')
  })

  it('bumps updated_at on rename', () => {
    const before = getDevcontainer('dc-seed-0002').updated_at
    updateDevcontainer('dc-seed-0002', { name: 'newname' })
    const after = getDevcontainer('dc-seed-0002').updated_at
    expect(after > before).toBe(true)
  })

  it('throws NotFoundError for unknown id', () => {
    expect(() => updateDevcontainer('nope', { name: 'x' })).toThrow(NotFoundError)
  })
})

describe('startDevcontainer', () => {
  it('sets status to "running"', () => {
    const result = startDevcontainer('dc-seed-0002')
    expect(result.status).toBe('running')
    expect(getDevcontainer('dc-seed-0002').status).toBe('running')
  })

  it('bumps updated_at', () => {
    const before = getDevcontainer('dc-seed-0002').updated_at
    startDevcontainer('dc-seed-0002')
    const after = getDevcontainer('dc-seed-0002').updated_at
    expect(after >= before).toBe(true)
  })

  it('throws NotFoundError for unknown id', () => {
    expect(() => startDevcontainer('nope')).toThrow(NotFoundError)
  })
})

describe('stopDevcontainer', () => {
  it('sets status to "stopped"', () => {
    const result = stopDevcontainer('dc-seed-0001')
    expect(result.status).toBe('stopped')
    expect(getDevcontainer('dc-seed-0001').status).toBe('stopped')
  })

  it('throws NotFoundError for unknown id', () => {
    expect(() => stopDevcontainer('nope')).toThrow(NotFoundError)
  })
})

describe('deleteDevcontainer', () => {
  it('removes the devcontainer from the list', () => {
    const before = listDevcontainers().items.length
    deleteDevcontainer('dc-seed-0003')
    expect(listDevcontainers().items.length).toBe(before - 1)
    expect(listDevcontainers().items.find((d) => d.id === 'dc-seed-0003')).toBeUndefined()
  })

  it('throws NotFoundError for unknown id', () => {
    expect(() => deleteDevcontainer('nope')).toThrow(NotFoundError)
  })
})

describe('resetDevcontainers', () => {
  it('restores seed after mutations', () => {
    deleteDevcontainer('dc-seed-0001')
    deleteDevcontainer('dc-seed-0002')
    resetDevcontainers()
    expect(listDevcontainers().items.length).toBeGreaterThanOrEqual(4)
    expect(getDevcontainer('dc-seed-0001').name).toBe('my-webapp')
  })
})
