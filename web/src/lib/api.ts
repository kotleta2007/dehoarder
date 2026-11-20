export interface Status {
  scans: number
  tabs: number
  books: number
  jobs: number
}

export async function getStatus(): Promise<Status> {
  const response = await fetch('/api/v1/status')
  if (!response.ok) {
    throw new Error(`GET /api/v1/status failed: ${response.status}`)
  }
  return (await response.json()) as Status
}

export interface BridgeStatus {
  connected: boolean
  extension_id: string | null
  version: string | null
  last_seen: string | null
}

export async function getBridgeStatus(): Promise<BridgeStatus> {
  const response = await fetch('/api/v1/bridge/status')
  if (!response.ok) {
    throw new Error(`GET /api/v1/bridge/status failed: ${response.status}`)
  }
  return (await response.json()) as BridgeStatus
}

/** The shape `chrome.tabs.query({})` (normalized by the extension) returns. */
export interface ChromeTab {
  windowId: number
  id: number
  url: string
  title: string | null
  discarded: boolean
  lastAccessed: number | null
  pinned: boolean
}

interface ScanTabPayload {
  windowId: number
  id: number
  url: string
  title: string | null
  discarded: boolean
  lastAccessed: number | null
}

export interface ScanPayload {
  tabs: ScanTabPayload[]
}

/** Drops fields the server doesn't persist (e.g. `pinned`) and normalizes
 * missing values to `null` for a clean JSON body. */
export function buildScanPayload(tabs: ChromeTab[]): ScanPayload {
  return {
    tabs: tabs.map((tab) => ({
      windowId: tab.windowId,
      id: tab.id,
      url: tab.url,
      title: tab.title ?? null,
      discarded: tab.discarded,
      lastAccessed: tab.lastAccessed ?? null,
    })),
  }
}

export interface TabOut {
  id: number
  url: string
  title: string | null
  domain: string
  discarded: boolean
  decision: string
}

export interface ScanOut {
  id: number
  started_at: string
  source: string
  profile_name: string | null
  tab_count: number
  tabs: TabOut[]
}

export async function createScan(tabs: ChromeTab[]): Promise<ScanOut> {
  const response = await fetch('/api/v1/scans', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(buildScanPayload(tabs)),
  })
  if (!response.ok) {
    throw new Error(`POST /api/v1/scans failed: ${response.status}`)
  }
  return (await response.json()) as ScanOut
}

/** Asks the extension (via `externally_connectable`) to list every tab in
 * this browser profile. Rejects if no extension is detected. */
export function listTabsFromExtension(extensionId: string): Promise<ChromeTab[]> {
  return new Promise((resolve, reject) => {
    if (typeof chrome === 'undefined' || !chrome.runtime?.sendMessage) {
      reject(new Error('chrome.runtime is not available'))
      return
    }
    chrome.runtime.sendMessage(extensionId, { type: 'list_tabs' }, (response: ChromeTab[]) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message))
        return
      }
      resolve(response)
    })
  })
}

export interface Profile {
  dir_name: string
  display_name: string
  current: boolean
}

export async function getProfiles(): Promise<Profile[]> {
  const response = await fetch('/api/v1/profiles')
  if (!response.ok) {
    throw new Error(`GET /api/v1/profiles failed: ${response.status}`)
  }
  return (await response.json()) as Profile[]
}

export async function createScanFromSnss(profileName: string | null): Promise<ScanOut> {
  const response = await fetch('/api/v1/scans/snss', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_name: profileName }),
  })
  if (!response.ok) {
    throw new Error(`POST /api/v1/scans/snss failed: ${response.status}`)
  }
  return (await response.json()) as ScanOut
}
