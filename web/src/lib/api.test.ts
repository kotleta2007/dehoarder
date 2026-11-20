import { describe, expect, it, vi } from 'vitest'
import {
  buildScanPayload,
  createScan,
  createScanFromSnss,
  getProfiles,
  getStatus,
  type ChromeTab,
} from './api'

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

describe('buildScanPayload', () => {
  it('drops fields the server does not persist and keeps the rest', () => {
    const tabs: ChromeTab[] = [
      {
        windowId: 1,
        id: 10,
        url: 'https://example.com/a',
        title: 'A',
        discarded: false,
        lastAccessed: 123,
        pinned: true,
      },
    ]

    expect(buildScanPayload(tabs)).toEqual({
      tabs: [
        {
          windowId: 1,
          id: 10,
          url: 'https://example.com/a',
          title: 'A',
          discarded: false,
          lastAccessed: 123,
        },
      ],
    })
  })

  it('normalizes missing title and lastAccessed to null', () => {
    const tabs: ChromeTab[] = [
      {
        windowId: 1,
        id: 10,
        url: 'https://example.com/a',
        title: null,
        discarded: false,
        lastAccessed: null,
        pinned: false,
      },
    ]

    const payload = buildScanPayload(tabs)
    expect(payload.tabs[0].title).toBeNull()
    expect(payload.tabs[0].lastAccessed).toBeNull()
  })
})

describe('createScan', () => {
  it('posts the normalized payload and returns the parsed scan', async () => {
    const tabs: ChromeTab[] = [
      {
        windowId: 1,
        id: 10,
        url: 'https://example.com/a',
        title: 'A',
        discarded: false,
        lastAccessed: null,
        pinned: false,
      },
    ]
    const scan = { id: 1, started_at: 'now', source: 'extension', tab_count: 1, tabs: [] }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => scan,
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(createScan(tabs)).resolves.toEqual(scan)

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/scans',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildScanPayload(tabs)),
      }),
    )
  })
})

describe('getProfiles', () => {
  it('returns the parsed profile list', async () => {
    const profiles = [{ dir_name: 'Default', display_name: 'Mark', current: true }]
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => profiles }),
    )

    await expect(getProfiles()).resolves.toEqual(profiles)
  })
})

describe('createScanFromSnss', () => {
  it('posts the chosen profile name', async () => {
    const scan = {
      id: 1,
      started_at: 'now',
      source: 'snss',
      profile_name: 'Mark',
      tab_count: 0,
      tabs: [],
    }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => scan })
    vi.stubGlobal('fetch', fetchMock)

    await expect(createScanFromSnss('Mark')).resolves.toEqual(scan)

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/scans/snss',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile_name: 'Mark' }),
      }),
    )
  })
})
