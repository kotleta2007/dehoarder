import type { Decision, TabOut } from './api'

/** One known shop in the review: all its open tabs share a per-shop toggle. */
export interface ShopGroup {
  shop: string
  name: string
  tabs: TabOut[]
  /** `close` / `keep` when every tab agrees, `mixed` otherwise. */
  decision: Decision | 'mixed'
}

/** One unknown domain that looks like a bookshop: Learn & close, or Keep. */
export interface DomainGroup {
  domain: string
  tabs: TabOut[]
  decision: Decision | 'mixed'
}

export interface Review {
  known: ShopGroup[]
  unknown: DomainGroup[]
  notBook: TabOut[]
  /** Not classified yet (classify job still running or not started). */
  unclassified: TabOut[]
}

function groupDecision(tabs: TabOut[]): Decision | 'mixed' {
  const first = tabs[0]?.decision ?? 'pending'
  return tabs.every((t) => t.decision === first) ? first : 'mixed'
}

function bySizeThenName<T extends { tabs: TabOut[] }>(key: (g: T) => string) {
  return (a: T, b: T) => b.tabs.length - a.tabs.length || key(a).localeCompare(key(b))
}

/** Splits a scan's open tabs into the three review groups. Groups are
 * largest first (RAM-first), ties by name. Already-closed tabs are left out. */
export function groupTabs(tabs: TabOut[]): Review {
  const shops = new Map<string, TabOut[]>()
  const domains = new Map<string, TabOut[]>()
  const notBook: TabOut[] = []
  const unclassified: TabOut[] = []

  for (const tab of tabs) {
    if (tab.closed_at) continue
    if (tab.classification === 'known_shop' && tab.shop) {
      shops.set(tab.shop, [...(shops.get(tab.shop) ?? []), tab])
    } else if (tab.classification === 'unknown_book') {
      domains.set(tab.domain, [...(domains.get(tab.domain) ?? []), tab])
    } else if (tab.classification === 'not_book') {
      notBook.push(tab)
    } else {
      unclassified.push(tab)
    }
  }

  const known = [...shops].map(([shop, group]) => ({
    shop,
    name: group[0].shop_name ?? shop,
    tabs: group,
    decision: groupDecision(group),
  }))
  const unknown = [...domains].map(([domain, group]) => ({
    domain,
    tabs: group,
    decision: groupDecision(group),
  }))

  return {
    known: known.sort(bySizeThenName((g) => g.name)),
    unknown: unknown.sort(bySizeThenName((g) => g.domain)),
    notBook,
    unclassified,
  }
}

export interface CloseButtonState {
  /** Open tabs approved for closing. */
  count: number
  /** Open tabs still waiting for a decision (or for classification). */
  pending: number
  disabled: boolean
}

/** "Close approved (N)" is enabled only when there is something to close
 * and nothing left undecided. */
export function closeButtonState(tabs: TabOut[]): CloseButtonState {
  const open = tabs.filter((t) => !t.closed_at)
  const count = open.filter((t) => t.decision === 'close').length
  const pending = open.filter((t) => t.decision === 'pending').length
  return { count, pending, disabled: count === 0 || pending > 0 }
}
