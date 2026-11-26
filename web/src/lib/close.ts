import type { ArchiveOut, ChromeTab, CloseItem, CloseResult, CloseSummary } from './api'

/** The steps of the close flow, injectable so the sequence can be tested
 * against a fake extension and server. */
export interface CloseDeps {
  archiveScan: (scanId: number) => Promise<ArchiveOut>
  listTabs: () => Promise<ChromeTab[]>
  closeTabs: (ids: number[]) => Promise<CloseResult>
  reportClosed: (
    scanId: number,
    outcome: { closed: number[]; missing: number[] },
  ) => Promise<CloseSummary>
}

export interface LiveMatch {
  /** tab id (server) → live browser tab id */
  pairs: { tabId: number; liveId: number }[]
  /** archived tabs with no live tab showing their URL */
  unmatched: number[]
}

/** Pairs each archived tab with a live tab that still shows its URL: the
 * same browser id if its URL is unchanged, otherwise any not-yet-used live
 * tab with that exact URL (ids change across browser restarts). A tab is
 * never closed on id alone, so a reused id can't close the wrong page. */
export function matchLiveTabs(toClose: CloseItem[], live: ChromeTab[]): LiveMatch {
  const byId = new Map(live.map((t) => [t.id, t]))
  const used = new Set<number>()
  const pairs: LiveMatch['pairs'] = []
  const unmatched: number[] = []

  for (const item of toClose) {
    const same = byId.get(item.browser_tab_id)
    if (same && same.url === item.url && !used.has(same.id)) {
      used.add(same.id)
      pairs.push({ tabId: item.tab_id, liveId: same.id })
    }
  }
  const paired = new Set(pairs.map((p) => p.tabId))
  for (const item of toClose) {
    if (paired.has(item.tab_id)) continue
    const other = live.find((t) => t.url === item.url && !used.has(t.id))
    if (other) {
      used.add(other.id)
      pairs.push({ tabId: item.tab_id, liveId: other.id })
    } else {
      unmatched.push(item.tab_id)
    }
  }
  return { pairs, unmatched }
}

/** Archive → match live tabs → close → report. If archiving fails, it
 * throws before anything is sent to the extension. */
export async function closeApproved(scanId: number, deps: CloseDeps): Promise<CloseSummary> {
  const archived = await deps.archiveScan(scanId)
  if (archived.to_close.length === 0) {
    return deps.reportClosed(scanId, { closed: [], missing: [] })
  }

  const { pairs, unmatched } = matchLiveTabs(archived.to_close, await deps.listTabs())
  const result =
    pairs.length > 0
      ? await deps.closeTabs(pairs.map((p) => p.liveId))
      : { closed: [], missing: [] }

  const closedLive = new Set(result.closed)
  return deps.reportClosed(scanId, {
    closed: pairs.filter((p) => closedLive.has(p.liveId)).map((p) => p.tabId),
    missing: [...pairs.filter((p) => !closedLive.has(p.liveId)).map((p) => p.tabId), ...unmatched],
  })
}
