import { describe, expect, it, vi } from 'vitest'
import type { RestoreItem } from './api'
import { restoreScan, type RestoreDeps } from './restore'

const items: RestoreItem[] = [
  { tab_id: 1, url: 'https://bookvoed.ru/product/1' },
  { tab_id: 2, url: 'https://bookvoed.ru/product/2' },
]

function fakeDeps(list: RestoreItem[]) {
  return {
    getRestoreList: vi.fn().mockResolvedValue(list),
    openTabs: vi.fn().mockResolvedValue(undefined),
    reportRestored: vi.fn(async (_scanId: number, ids: number[]) => ({ restored: ids.length })),
  } satisfies RestoreDeps
}

describe('restoreScan', () => {
  it('opens the archived URLs and reports their tab ids', async () => {
    const deps = fakeDeps(items)

    await expect(restoreScan(3, true, deps)).resolves.toBe(2)

    expect(deps.getRestoreList).toHaveBeenCalledWith(3, true)
    expect(deps.openTabs).toHaveBeenCalledWith([items[0].url, items[1].url])
    expect(deps.reportRestored).toHaveBeenCalledWith(3, [1, 2])
    expect(deps.openTabs.mock.invocationCallOrder[0]).toBeLessThan(
      deps.reportRestored.mock.invocationCallOrder[0],
    )
  })

  it('records nothing if the extension fails to open the tabs', async () => {
    const deps = fakeDeps(items)
    deps.openTabs.mockRejectedValue(new Error('Could not establish connection'))

    await expect(restoreScan(3, false, deps)).rejects.toThrow('connection')
    expect(deps.reportRestored).not.toHaveBeenCalled()
  })

  it('does nothing when the restore list is empty', async () => {
    const deps = fakeDeps([])
    await expect(restoreScan(3, false, deps)).resolves.toBe(0)
    expect(deps.openTabs).not.toHaveBeenCalled()
    expect(deps.reportRestored).not.toHaveBeenCalled()
  })
})
