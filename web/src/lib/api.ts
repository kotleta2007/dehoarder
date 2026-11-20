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

export type Classification = 'known_shop' | 'unknown_book' | 'not_book'
export type Decision = 'close' | 'keep' | 'pending'

export interface TabOut {
  id: number
  url: string
  title: string | null
  domain: string
  discarded: boolean
  decision: Decision
  classification: Classification | null
  shop: string | null
  shop_name: string | null
  closed_at: string | null
}

export interface ScanOut {
  id: number
  started_at: string
  source: string
  profile_name: string | null
  tab_count: number
  tabs: TabOut[]
  classify_job_id: number | null
}

export interface Job {
  id: number
  kind: string
  status: 'running' | 'done' | 'failed'
  stage: string | null
  progress: Record<string, unknown>
  error: string | null
}

async function send<T>(method: string, url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    let detail = ''
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? ''
    } catch {
      // body was not JSON; the status code is enough
    }
    throw new Error(`${method} ${url} failed: ${response.status}${detail ? ` — ${detail}` : ''}`)
  }
  return (await response.json()) as T
}

export function getTabs(scanId: number): Promise<TabOut[]> {
  return send('GET', `/api/v1/tabs?scan=${scanId}`)
}

export function setTabDecision(tabId: number, decision: Decision): Promise<TabOut> {
  return send('PATCH', `/api/v1/tabs/${tabId}`, { decision })
}

/** Set the decision for every open tab of a scan in one shop or on one domain. */
export function setTabsDecision(
  scanId: number,
  filter: { shop: string } | { domain: string },
  decision: Decision,
): Promise<{ updated: number }> {
  const params = new URLSearchParams({ scan: String(scanId), ...filter })
  return send('PATCH', `/api/v1/tabs?${params.toString()}`, { decision })
}

export interface Shop {
  id: number
  slug: string
  name: string
  domains: string[]
  kind: string
  currency: string | null
  extractor: string | null
  learned: boolean
}

export function learnShop(domain: string, name = ''): Promise<Shop> {
  return send('POST', '/api/v1/shops/learn', { domain, name })
}

export interface CloseItem {
  tab_id: number
  browser_tab_id: number
  url: string
}

export interface ArchiveOut {
  archived: number
  total: number
  path: string
  /** The only tabs the web app may ask the extension to close. */
  to_close: CloseItem[]
}

export interface CloseSummary {
  closed: number
  failed: number
  kept: number
}

export interface ScanSummary extends CloseSummary {
  id: number
  started_at: string
  source: string
  profile_name: string | null
  tab_count: number
}

export function archiveScan(scanId: number): Promise<ArchiveOut> {
  return send('POST', `/api/v1/scans/${scanId}/archive`)
}

/** Reports the close outcome by tab id (not browser tab id). */
export function reportClosed(
  scanId: number,
  outcome: { closed: number[]; missing: number[] },
): Promise<CloseSummary> {
  return send('POST', `/api/v1/scans/${scanId}/closed`, outcome)
}

export function getScans(): Promise<ScanSummary[]> {
  return send('GET', '/api/v1/scans')
}

export function startJob(kind: string): Promise<Job> {
  return send('POST', `/api/v1/jobs/${kind}`)
}

export function getJob(jobId: number): Promise<Job> {
  return send('GET', `/api/v1/jobs/${jobId}`)
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

/** Sends one message to the extension (via `externally_connectable`).
 * Rejects if no extension is detected or it reports an error. */
function sendToExtension<T>(
  extensionId: string,
  message: { type: string; payload?: unknown },
): Promise<T> {
  return new Promise((resolve, reject) => {
    if (typeof chrome === 'undefined' || !chrome.runtime?.sendMessage) {
      reject(new Error('chrome.runtime is not available'))
      return
    }
    chrome.runtime.sendMessage(extensionId, message, (response: T) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message))
        return
      }
      resolve(response)
    })
  })
}

/** Lists every tab in this browser profile. */
export function listTabsFromExtension(extensionId: string): Promise<ChromeTab[]> {
  return sendToExtension(extensionId, { type: 'list_tabs' })
}

export interface CloseResult {
  closed: number[]
  missing: number[]
}

/** Closes live browser tabs by id. Only ever called from `closeApproved`. */
export function closeTabsInBrowser(extensionId: string, ids: number[]): Promise<CloseResult> {
  return sendToExtension(extensionId, { type: 'close_tabs', payload: { ids } })
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
