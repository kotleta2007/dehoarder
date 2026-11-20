import type { RestoreItem } from './api'

export interface RestoreDeps {
  getRestoreList: (scanId: number, onlyFailed: boolean) => Promise<RestoreItem[]>
  openTabs: (urls: string[]) => Promise<void>
  reportRestored: (scanId: number, tabIds: number[]) => Promise<{ restored: number }>
}

/** Restore list → open_tabs → report. Tabs are recorded as restored only
 * after the extension has opened them; if opening fails nothing is
 * recorded, so the tabs stay in the restore list for another try. */
export async function restoreScan(
  scanId: number,
  onlyFailed: boolean,
  deps: RestoreDeps,
): Promise<number> {
  const items = await deps.getRestoreList(scanId, onlyFailed)
  if (items.length === 0) return 0
  await deps.openTabs(items.map((i) => i.url))
  const { restored } = await deps.reportRestored(
    scanId,
    items.map((i) => i.tab_id),
  )
  return restored
}
