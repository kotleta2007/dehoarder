import { describe, expect, it, vi } from 'vitest'
import { getStatus } from './api'

describe('getStatus', () => {
  it('returns the parsed status on a 200', async () => {
    const status = { scans: 1, tabs: 2, books: 3, jobs: 4 }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => status,
      }),
    )

    await expect(getStatus()).resolves.toEqual(status)
    expect(fetch).toHaveBeenCalledWith('/api/v1/status')
  })

  it('throws with the status code on a non-2xx response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({}),
      }),
    )

    await expect(getStatus()).rejects.toThrow('500')
  })
})
