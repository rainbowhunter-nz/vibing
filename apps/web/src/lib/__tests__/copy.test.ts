import { describe, it, expect } from 'vitest'
import { loadError } from '../copy'

describe('loadError', () => {
  it('builds a titled error message for the subject', () => {
    expect(loadError('devcontainers')).toEqual({
      title: "Couldn't load devcontainers",
      helper: 'Check that the backend is running, then reload the page.',
    })
  })
})
