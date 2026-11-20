// Dehoarder bridge service worker.
//
// Talks to the web app via chrome.runtime.onMessageExternal and to the
// server via a plain POST for the hello handshake. Pure functions are
// exported for unit testing (extension/tests/); the wiring at the bottom
// only runs inside an actual extension context.

const BRIDGE_HELLO_URL = 'http://127.0.0.1:8765/api/v1/bridge/hello'
const CLOSE_BATCH_SIZE = 50
const OPEN_BATCH_SIZE = 20
const OPEN_BATCH_DELAY_MS = 500

export function chunk(items, size) {
  const chunks = []
  for (let i = 0; i < items.length; i += size) {
    chunks.push(items.slice(i, i + size))
  }
  return chunks
}

function defaultSleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export function normalizeTabs(tabs) {
  return tabs.map((tab) => ({
    windowId: tab.windowId,
    id: tab.id,
    url: tab.url,
    title: tab.title,
    discarded: tab.discarded,
    lastAccessed: tab.lastAccessed,
    pinned: tab.pinned,
  }))
}

export async function listTabs(chromeApi) {
  const tabs = await chromeApi.tabs.query({})
  return normalizeTabs(tabs)
}

export async function closeTabs(chromeApi, ids) {
  const closed = []
  const missing = []
  for (const batch of chunk(ids, CLOSE_BATCH_SIZE)) {
    try {
      await chromeApi.tabs.remove(batch)
      closed.push(...batch)
    } catch {
      missing.push(...batch)
    }
  }
  return { closed, missing }
}

export async function openTabs(chromeApi, urls, sleepFn = defaultSleep) {
  const batches = chunk(urls, OPEN_BATCH_SIZE)
  for (let i = 0; i < batches.length; i++) {
    for (const url of batches[i]) {
      await chromeApi.tabs.create({ url, active: false })
    }
    if (i < batches.length - 1) {
      await sleepFn(OPEN_BATCH_DELAY_MS)
    }
  }
}

export function buildHelloPayload(chromeApi) {
  return {
    extension_id: chromeApi.runtime.id,
    version: chromeApi.runtime.getManifest().version,
  }
}

export async function sendHello(chromeApi, fetchFn) {
  return fetchFn(BRIDGE_HELLO_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(buildHelloPayload(chromeApi)),
  })
}

export async function handleMessage(chromeApi, message) {
  switch (message.type) {
    case 'list_tabs':
      return listTabs(chromeApi)
    case 'close_tabs':
      return closeTabs(chromeApi, message.payload.ids)
    case 'open_tabs':
      return openTabs(chromeApi, message.payload.urls)
    default:
      throw new Error(`unknown message type: ${message.type}`)
  }
}

/* c8 ignore start -- wiring only runs inside an actual extension context */
if (typeof chrome !== 'undefined' && chrome.runtime?.onInstalled) {
  chrome.runtime.onInstalled.addListener(() => sendHello(chrome, fetch))
  chrome.runtime.onStartup.addListener(() => sendHello(chrome, fetch))

  chrome.runtime.onMessageExternal.addListener((message, _sender, sendResponse) => {
    handleMessage(chrome, message).then(sendResponse)
    return true
  })
}
/* c8 ignore stop */
