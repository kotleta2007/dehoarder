import { describe, expect, it } from 'vitest'
import type { TabOut } from './api'
import { closeButtonState, groupTabs } from './review'

let nextId = 1

function tab(overrides: Partial<TabOut>): TabOut {
  return {
    id: nextId++,
    url: 'https://example.com/',
    title: null,
    domain: 'example.com',
    discarded: true,
    decision: 'pending',
    classification: null,
    shop: null,
    shop_name: null,
    closed_at: null,
    ...overrides,
  }
}

const amazon = (decision: TabOut['decision'] = 'close') =>
  tab({
    domain: 'amazon.de',
    classification: 'known_shop',
    shop: 'amazon',
    shop_name: 'Amazon',
    decision,
  })
const manning = () =>
  tab({
    domain: 'manning.com',
    classification: 'known_shop',
    shop: 'manning',
    shop_name: 'Manning',
    decision: 'close',
  })
const labirint = (decision: TabOut['decision'] = 'pending') =>
  tab({ domain: 'labirint.ru', classification: 'unknown_book', decision })
const github = () => tab({ domain: 'github.com', classification: 'not_book', decision: 'keep' })

describe('groupTabs', () => {
  it('splits tabs into known shops, unknown domains and non-books', () => {
    const review = groupTabs([amazon(), manning(), amazon(), labirint(), github(), tab({})])

    expect(review.known.map((g) => [g.shop, g.name, g.tabs.length])).toEqual([
      ['amazon', 'Amazon', 2],
      ['manning', 'Manning', 1],
    ])
    expect(review.unknown.map((g) => [g.domain, g.tabs.length])).toEqual([['labirint.ru', 1]])
    expect(review.notBook).toHaveLength(1)
    expect(review.unclassified).toHaveLength(1)
  })

  it('reports a group decision, or mixed when the tabs disagree', () => {
    const review = groupTabs([amazon('close'), amazon('keep'), manning(), labirint('keep')])
    expect(review.known.find((g) => g.shop === 'amazon')?.decision).toBe('mixed')
    expect(review.known.find((g) => g.shop === 'manning')?.decision).toBe('close')
    expect(review.unknown[0].decision).toBe('keep')
  })

  it('leaves out tabs that are already closed', () => {
    const review = groupTabs([amazon(), { ...amazon(), closed_at: '2026-11-20T10:00:00Z' }])
    expect(review.known[0].tabs).toHaveLength(1)
  })

  it('orders groups largest first, then by name', () => {
    const a = tab({ domain: 'a.ru', classification: 'unknown_book' })
    const b = tab({ domain: 'b.ru', classification: 'unknown_book' })
    const review = groupTabs([b, a, labirint(), labirint()])
    expect(review.unknown.map((g) => g.domain)).toEqual(['labirint.ru', 'a.ru', 'b.ru'])
  })
})

describe('closeButtonState', () => {
  it('is disabled while any tab is still pending', () => {
    expect(closeButtonState([amazon(), labirint('pending')])).toEqual({
      count: 1,
      pending: 1,
      disabled: true,
    })
  })

  it('is enabled once every tab is decided and something is approved', () => {
    expect(closeButtonState([amazon(), amazon(), labirint('keep'), github()])).toEqual({
      count: 2,
      pending: 0,
      disabled: false,
    })
  })

  it('is disabled when nothing is approved for closing', () => {
    expect(closeButtonState([amazon('keep'), github()]).disabled).toBe(true)
    expect(closeButtonState([]).disabled).toBe(true)
  })

  it('ignores tabs that are already closed', () => {
    const closed = { ...labirint('pending'), closed_at: '2026-11-20T10:00:00Z' }
    expect(closeButtonState([amazon(), closed])).toEqual({ count: 1, pending: 0, disabled: false })
  })
})
