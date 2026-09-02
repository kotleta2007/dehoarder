export const VIEWS = ['Tabs', 'Progress', 'Graph', 'Plan'] as const

export type View = (typeof VIEWS)[number]
