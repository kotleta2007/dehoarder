import { describe, expect, it, vi } from 'vitest'
import type { ArchiveOut, ChromeTab, CloseItem } from './api'
import { closeApproved, matchLiveTabs, type CloseDeps } from './close'

const live = (id: number, url: string): ChromeTab => ({
  windowId: 1,
  id,
  url,
  title: null,
  discarded: true,
  lastAccessed: null,
  pinned: false,
})

const item = (tabId: number, browserId: number, url: string): CloseItem => ({
  tab_id: tabId,
  browser_tab_id: browserId,
  url,
})

const A = 'https://www.manning.com/books/a'
const B = 'https://www.manning.com/books/b'
const C = 'https://www.manning.com/books/c'

describe('matchLiveTabs', () => {
  it('pairs by browser id when the URL is unchanged', () => {
    expect(matchLiveTabs([item(1, 10, A)], [live(10, A)])).toEqual({
      pairs: [{ tabId: 1, liveId: 10 }],
      unmatched: [],
    })
  })

  it('never closes a reused id that now shows a different page', () => {
    const result = matchLiveTabs([item(1, 10, A)], [live(10, 'https://mail.example.com/')])
    expect(result).toEqual({ pairs: [], unmatched: [1] })
  })

  it('falls back to a live tab with the same URL when the id changed', () => {
    expect(matchLiveTabs([item(1, 10, A)], [live(77, A)]).pairs).toEqual([{ tabId: 1, liveId: 77 }])
  })

  it('uses each live tab at most once for duplicate URLs', () => {
    const result = matchLiveTabs(
      [item(1, 10, A), item(2, 11, A), item(3, 12, A)],
      [live(11, A), live(90, A)],
    )
    expect(result.pairs).toEqual([
      { tabId: 2, liveId: 11 },
      { tabId: 1, liveId: 90 },
    ])
    expect(result.unmatched).toEqual([3])
  })
})

function fakeDeps(archive: Partial<ArchiveOut>, liveTabs: ChromeTab[], missingLive: number[] = []) {
  const deps = {
    archiveScan: vi
      .fn()
      .mockResolvedValue({ archived: 0, total: 0, path: 'x', to_close: [], ...archive }),
    listTabs: vi.fn().mockResolvedValue(liveTabs),
    closeTabs: vi.fn(async (ids: number[]) => ({
      closed: ids.filter((id) => !missingLive.includes(id)),
      missing: ids.filter((id) => missingLive.includes(id)),
    })),
    reportClosed: vi.fn().mockResolvedValue({ closed: 0, failed: 0, kept: 0 }),
  } satisfies CloseDeps
  return deps
}

describe('closeApproved', () => {
  it('archives, closes only matched live tabs, and reports by tab id', async () => {
    const deps = fakeDeps(
      { to_close: [item(1, 10, A), item(2, 11, B), item(3, 12, C)] },
      [live(10, A), live(11, B), live(12, 'https://other.example/')],
      [11],
    )

    await closeApproved(7, deps)

    expect(deps.archiveScan).toHaveBeenCalledWith(7)
    expect(deps.closeTabs).toHaveBeenCalledWith([10, 11])
    expect(deps.reportClosed).toHaveBeenCalledWith(7, { closed: [1], missing: [2, 3] })
    // order: archive before anything reaches the extension
    expect(deps.archiveScan.mock.invocationCallOrder[0]).toBeLessThan(
      deps.closeTabs.mock.invocationCallOrder[0],
    )
  })

  it('sends nothing to the extension if archiving fails', async () => {
    const deps = fakeDeps({}, [live(10, A)])
    deps.archiveScan.mockRejectedValue(new Error('POST /archive failed: 500'))

    await expect(closeApproved(7, deps)).rejects.toThrow('500')
    expect(deps.listTabs).not.toHaveBeenCalled()
    expect(deps.closeTabs).not.toHaveBeenCalled()
    expect(deps.reportClosed).not.toHaveBeenCalled()
  })

  it('does not call close_tabs when no archived tab is still open', async () => {
    const deps = fakeDeps({ to_close: [item(1, 10, A)] }, [])
    await closeApproved(7, deps)
    expect(deps.closeTabs).not.toHaveBeenCalled()
    expect(deps.reportClosed).toHaveBeenCalledWith(7, { closed: [], missing: [1] })
  })

  it('skips listing and closing when there is nothing to close', async () => {
    const deps = fakeDeps({ to_close: [] }, [live(10, A)])
    await closeApproved(7, deps)
    expect(deps.listTabs).not.toHaveBeenCalled()
    expect(deps.closeTabs).not.toHaveBeenCalled()
  })
})
