import { describe, expect, it, vi } from 'vitest'
import {
  buildHelloPayload,
  chunk,
  closeTabs,
  handleMessage,
  listTabs,
  normalizeTabs,
  openTabs,
  sendHello,
} from '../background.js'

function fakeChrome({ removeError = null } = {}) {
  return {
    tabs: {
      query: vi.fn().mockResolvedValue([
        {
          windowId: 1,
          id: 10,
          url: 'https://example.com/a',
          title: 'A',
          discarded: false,
          lastAccessed: 100,
          pinned: false,
          extraNoise: 'should be dropped',
        },
      ]),
      remove: removeError ? vi.fn().mockRejectedValue(removeError) : vi.fn().mockResolvedValue(undefined),
      create: vi.fn().mockResolvedValue(undefined),
    },
    runtime: {
      id: 'abc123',
      getManifest: () => ({ version: '0.1.0' }),
    },
  }
}

describe('chunk', () => {
  it('splits into batches of the given size', () => {
    expect(chunk([1, 2, 3, 4, 5], 2)).toEqual([[1, 2], [3, 4], [5]])
  })

  it('returns one chunk when smaller than the batch size', () => {
    expect(chunk([1, 2], 50)).toEqual([[1, 2]])
  })
})

describe('normalizeTabs', () => {
  it('keeps only the fields the server cares about', () => {
    const raw = [
      { windowId: 1, id: 10, url: 'u', title: 't', discarded: true, lastAccessed: 1, pinned: false, junk: 1 },
    ]
    expect(normalizeTabs(raw)).toEqual([
      { windowId: 1, id: 10, url: 'u', title: 't', discarded: true, lastAccessed: 1, pinned: false },
    ])
  })
})

describe('listTabs', () => {
  it('queries all tabs and normalizes them', async () => {
    const chromeApi = fakeChrome()
    const result = await listTabs(chromeApi)
    expect(chromeApi.tabs.query).toHaveBeenCalledWith({})
    expect(result).toEqual([
      { windowId: 1, id: 10, url: 'https://example.com/a', title: 'A', discarded: false, lastAccessed: 100, pinned: false },
    ])
  })
})

describe('closeTabs', () => {
  it('reports every id as closed when remove succeeds', async () => {
    const chromeApi = fakeChrome()
    const ids = Array.from({ length: 75 }, (_, i) => i)

    const result = await closeTabs(chromeApi, ids)

    expect(chromeApi.tabs.remove).toHaveBeenCalledTimes(2)
    expect(chromeApi.tabs.remove).toHaveBeenNthCalledWith(1, ids.slice(0, 50))
    expect(chromeApi.tabs.remove).toHaveBeenNthCalledWith(2, ids.slice(50))
    expect(result).toEqual({ closed: ids, missing: [] })
  })

  it('reports every id as missing when no tab can be removed', async () => {
    const chromeApi = fakeChrome({ removeError: new Error('no such tab') })
    const result = await closeTabs(chromeApi, [1, 2, 3])
    expect(result).toEqual({ closed: [], missing: [1, 2, 3] })
  })

  it('retries a failed batch tab by tab so one stale id does not block the rest', async () => {
    const chromeApi = fakeChrome()
    chromeApi.tabs.remove.mockImplementation(async (arg) => {
      const ids = Array.isArray(arg) ? arg : [arg]
      if (ids.includes(2)) throw new Error('No tab with id: 2')
    })

    const result = await closeTabs(chromeApi, [1, 2, 3])

    expect(result).toEqual({ closed: [1, 3], missing: [2] })
    expect(chromeApi.tabs.remove).toHaveBeenCalledWith([1, 2, 3])
    expect(chromeApi.tabs.remove).toHaveBeenCalledWith(1)
    expect(chromeApi.tabs.remove).toHaveBeenCalledWith(3)
  })
})

describe('openTabs', () => {
  it('creates tabs inactive, in batches of 20, sleeping between batches only', async () => {
    const chromeApi = fakeChrome()
    const sleepFn = vi.fn().mockResolvedValue(undefined)
    const urls = Array.from({ length: 45 }, (_, i) => `https://example.com/${i}`)

    await openTabs(chromeApi, urls, sleepFn)

    expect(chromeApi.tabs.create).toHaveBeenCalledTimes(45)
    expect(chromeApi.tabs.create).toHaveBeenCalledWith({ url: urls[0], active: false })
    expect(sleepFn).toHaveBeenCalledTimes(2)
    expect(sleepFn).toHaveBeenCalledWith(500)
  })

  it('does not sleep when everything fits in one batch', async () => {
    const chromeApi = fakeChrome()
    const sleepFn = vi.fn().mockResolvedValue(undefined)

    await openTabs(chromeApi, ['https://example.com/a'], sleepFn)

    expect(sleepFn).not.toHaveBeenCalled()
  })
})

describe('buildHelloPayload', () => {
  it('reads the extension id and manifest version', () => {
    const chromeApi = fakeChrome()
    expect(buildHelloPayload(chromeApi)).toEqual({ extension_id: 'abc123', version: '0.1.0' })
  })
})

describe('sendHello', () => {
  it('posts the hello payload as JSON', async () => {
    const chromeApi = fakeChrome()
    const fetchFn = vi.fn().mockResolvedValue({ ok: true })

    await sendHello(chromeApi, fetchFn)

    expect(fetchFn).toHaveBeenCalledWith(
      'http://127.0.0.1:8765/api/v1/bridge/hello',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ extension_id: 'abc123', version: '0.1.0' }),
      }),
    )
  })
})

describe('handleMessage', () => {
  it('dispatches list_tabs', async () => {
    const chromeApi = fakeChrome()
    const result = await handleMessage(chromeApi, { type: 'list_tabs' })
    expect(result).toHaveLength(1)
  })

  it('dispatches close_tabs with its payload', async () => {
    const chromeApi = fakeChrome()
    const result = await handleMessage(chromeApi, { type: 'close_tabs', payload: { ids: [1, 2] } })
    expect(result).toEqual({ closed: [1, 2], missing: [] })
  })

  it('dispatches open_tabs with its payload', async () => {
    const chromeApi = fakeChrome()
    await handleMessage(chromeApi, { type: 'open_tabs', payload: { urls: ['https://example.com/a'] } })
    expect(chromeApi.tabs.create).toHaveBeenCalledWith({ url: 'https://example.com/a', active: false })
  })

  it('throws on an unknown message type', async () => {
    const chromeApi = fakeChrome()
    await expect(handleMessage(chromeApi, { type: 'nonsense' })).rejects.toThrow('unknown message type')
  })
})
