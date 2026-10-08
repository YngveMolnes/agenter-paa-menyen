import type { CartView, Dinner } from '../types'

type CartItem = {
  ean: string
  quantity: number
  pricePerUnit: number
  __removed__?: boolean
  doesNotExistInCurrentStore?: boolean
  product?: {
    title?: string
    subtitle?: string
    isOutOfStock?: boolean
    isForSale?: boolean
    availableInventory?: number | null
    isOffer?: boolean
    pricePerUnitOriginal?: number
  }
}

/** Mirrors Meny.unavailable: what meny.no shows as "Midlertidig utsolgt". */
export function isUnavailable(item: CartItem): boolean {
  const p = item.product ?? {}
  return Boolean(
    item.doesNotExistInCurrentStore ||
      p.isOutOfStock ||
      p.isForSale === false ||
      (p.availableInventory != null && p.availableInventory <= 0),
  )
}

/** Summarise `matlevering cart --json` output. */
export function summarizeCart(json: string): CartView {
  const cart = JSON.parse(json) as { items?: CartItem[] }
  const lines = (cart.items ?? [])
    .filter(item => !item.__removed__)
    .map(item => ({
      ean: item.ean,
      title: [item.product?.title, item.product?.subtitle].filter(Boolean).join(' ') || item.ean,
      quantity: item.quantity,
      lineTotal: item.pricePerUnit * item.quantity,
      isUnavailable: isUnavailable(item),
      isOffer: item.product?.isOffer === true,
      saved:
        item.product?.isOffer && item.product.pricePerUnitOriginal
          ? Math.max(0, (item.product.pricePerUnitOriginal - item.pricePerUnit) * item.quantity)
          : 0,
    }))
  return {
    lines,
    total: lines.reduce((sum, line) => sum + line.lineTotal, 0),
    unavailableCount: lines.filter(line => line.isUnavailable).length,
    saved: lines.reduce((sum, line) => sum + line.saved, 0),
  }
}

const stripMarkdown = (text: string) => text.replace(/\*\*|__|`/g, '').trim()

/**
 * The dinners from a meal plan: the first table under a "## ... Dinner ..."
 * heading, day in the first column and the dish in the second.
 */
export function parseDinners(markdown: string): Dinner[] {
  const lines = markdown.split('\n')
  const start = lines.findIndex(line => /^##\s.*(dinner|middag)/i.test(line))
  if (start < 0) return []
  const dinners: Dinner[] = []
  for (const line of lines.slice(start + 1)) {
    if (/^##\s/.test(line)) break
    if (!line.trim().startsWith('|')) {
      if (dinners.length > 0) break
      continue
    }
    const [day, dish] = line.split('|').slice(1, -1).map(cell => cell.trim())
    if (day === undefined || dish === undefined) continue
    if (/^:?-+:?$/.test(day) || /^(day|dag)$/i.test(day)) continue
    dinners.push({ day: stripMarkdown(day), dish: stripMarkdown(dish) })
  }
  return dinners
}

/** Last non-empty line of a command's error output, for showing in the pane. */
export function lastLine(text: string): string {
  return text.trim().split('\n').filter(Boolean).pop() ?? ''
}

/** 2121.28 -> "2 121 kr" */
export function kroner(amount: number): string {
  return `${Math.round(amount).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ')} kr`
}

const WEEKDAYS = [
  ['sun', 'søn'],
  ['mon', 'man'],
  ['tue', 'tir'],
  ['wed', 'ons'],
  ['thu', 'tor'],
  ['fri', 'fre'],
  ['sat', 'lør'],
] as const

/**
 * Where a plan's day label sits relative to today this week: -1 before,
 * 0 today, 1 later, undefined when the label isn't a weekday.
 */
export function relativeDay(label: string, today: number): -1 | 0 | 1 | undefined {
  const key = label.trim().toLowerCase().slice(0, 3)
  const index = WEEKDAYS.findIndex(names => (names as readonly string[]).includes(key))
  if (index < 0) return undefined
  // Weeks start on Monday: Sunday counts as the last day.
  const position = (index + 6) % 7
  const now = (today + 6) % 7
  return position < now ? -1 : position === now ? 0 : 1
}
