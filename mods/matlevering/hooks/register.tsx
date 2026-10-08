import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderChildren } from 'claude-code'

import type { CartView, DinnerPlan } from '../types'
import { kroner, lastLine, parseDinners, relativeDay, summarizeCart } from './parse'

const PANE = 'matlevering'
const TITLE = 'Matlevering'
const REFRESH_MS = 5 * 60 * 1000
const PLAN_FILE = /(^|\/)plans\/meal-plan[^/]*\.md$/

const cart = atom({ plugin: 'matlevering', key: 'cart' } as const, null as CartView | null)
const cartError = atom({ plugin: 'matlevering', key: 'cartError' } as const, null as string | null)
const store = atom({ plugin: 'matlevering', key: 'store' } as const, null as string | null)
const plan = atom({ plugin: 'matlevering', key: 'plan' } as const, null as DinnerPlan | null)
const isLoading = atom({ plugin: 'matlevering', key: 'isLoading' } as const, false)
const updatedAt = atom({ plugin: 'matlevering', key: 'updatedAt' } as const, 0)

let isRepo = false
let isRefreshing = false

async function loadPlan($: EngineInterface) {
  if (!(await $.fs.exists('plans'))) return update($, plan, () => null)
  const files = (await $.fs.list('plans'))
    .filter(f => f.kind === 'file' && /^meal-plan.*\.md$/.test(f.name))
    .sort((a, b) => b.mtimeMs - a.mtimeMs)
  const newest = files[0]
  if (!newest) return update($, plan, () => null)
  const text = await $.fs.read(`plans/${newest.name}`)
  await update($, plan, () => ({ file: newest.name, dinners: parseDinners(text) }))
}

async function loadCart($: EngineInterface) {
  const run = (args: string[]) =>
    $.process.run(['uv', 'run', 'matlevering', ...args], { timeoutMs: 60_000 })
  const [cartRun, storeRun] = await Promise.all([run(['cart', '--json']), run(['store'])])
  if (cartRun.exitCode !== 0) {
    await update($, cartError, () => lastLine(cartRun.stderr) || 'Could not read the basket.')
    return
  }
  const view = summarizeCart(cartRun.stdout)
  await update($, cart, () => view)
  await update($, cartError, () => null)
  await update($, store, () => (storeRun.exitCode === 0 ? (storeRun.stdout.split('\n')[0] ?? '').trim() : null))
  $.ui.status(
    `Basket: ${view.lines.length} items, ${kroner(view.total)}` +
      (view.unavailableCount ? `, ${view.unavailableCount} unavailable` : ''),
  )
}

async function refresh($: EngineInterface, what: 'all' | 'cart' | 'plan' = 'all') {
  if (!isRepo || isRefreshing) return
  isRefreshing = true
  await update($, isLoading, () => true)
  try {
    await Promise.all([
      what !== 'plan' ? loadCart($) : undefined,
      what !== 'cart' ? loadPlan($) : undefined,
    ])
    await update($, updatedAt, () => Date.now())
  } catch (err) {
    await update($, cartError, () => (err instanceof Error ? err.message : String(err)))
  } finally {
    isRefreshing = false
    await update($, isLoading, () => false)
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    isRepo = await $.fs.exists('src/matlevering/meny.py')
    if (!isRepo) return started

    await $.command.register({
      name: 'meny',
      description: 'Show the meny.no basket and planned dinners (refreshes them)',
    })
    void $.ui.open({ id: PANE, title: TITLE })
    void refresh($)
    $.clock.every(REFRESH_MS, () => void refresh($, 'cart'))

    return started
  })

  on('command.run', { command: 'meny' }, async $ => {
    await $.ui.open({ id: PANE, title: TITLE })
    await refresh($)
    const view = await read($, cart)
    return { text: view ? `Basket: ${view.lines.length} items, ${kroner(view.total)}.` : 'Basket refreshed.' }
  })

  // Keep the pane current when the basket or a plan changes during the session.
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const ran = await next(e)
    if (isRepo && /matlevering|examples\/add_from_list/.test(e.command)) void refresh($, 'cart')
    return ran
  }).catch(($, e, next) => next(e))
  on('tool.call', { tool: 'Write' }, async ($, e, next) => {
    const ran = await next(e)
    if (isRepo && PLAN_FILE.test(e.file_path)) void refresh($, 'plan')
    return ran
  }).catch(($, e, next) => next(e))
  on('tool.call', { tool: 'Edit' }, async ($, e, next) => {
    const ran = await next(e)
    if (isRepo && PLAN_FILE.test(e.file_path)) void refresh($, 'plan')
    return ran
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const [view, error, storeName, dinnerPlan, loading, at] = await Promise.all([
      read($, cart),
      read($, cartError),
      read($, store),
      read($, plan),
      read($, isLoading),
      read($, updatedAt),
    ])
    const rows = e.viewport?.rows ?? 30
    const dinners = dinnerPlan?.dinners ?? []
    const lines = view?.lines ?? []
    // Header 2, dinner card title + borders 3, basket card title + borders +
    // footer 5, the spacing between cards 1.
    const room = Math.max(3, rows - 11 - Math.max(1, dinners.length))
    // Unavailable items first, so they're never the ones cut off.
    const shown = [...lines.filter(l => l.isUnavailable), ...lines.filter(l => !l.isUnavailable)]
    const hidden = Math.max(0, shown.length - room)
    const today = new Date().getDay()
    const time = at ? new Date(at).toTimeString().slice(0, 5) : ''

    const Card = ({ title, aside, color, children }: {
      title: string
      aside?: string
      color: string
      children?: RenderChildren
    }) => (
      <Box flexDirection="column" borderStyle="round" borderColor={color} paddingX={1}>
        <Box justifyContent="space-between">
          <Text bold color={color}>{title}</Text>
          {aside ? <Text dimColor>{aside}</Text> : null}
        </Box>
        {children}
      </Box>
    )

    const Row = ({ left, right, color, dim }: {
      left: RenderChildren
      right: RenderChildren
      color?: string
      dim?: boolean
    }) => (
      <Box justifyContent="space-between">
        <Box flexShrink={1} flexGrow={1}>
          <Text wrap="truncate-end" color={color} dimColor={dim}>{left}</Text>
        </Box>
        <Box flexShrink={0} marginLeft={1}>
          <Text color={color} dimColor={dim}>{right}</Text>
        </Box>
      </Box>
    )

    return (
      <Box flexDirection="column">
        <Box justifyContent="space-between" paddingX={1}>
          <Text bold>🛒 Matlevering</Text>
          <Text dimColor>
            {loading ? '↻ updating…' : time ? `updated ${time}` : ''}
          </Text>
        </Box>

        <Card title="Dinners" aside={dinnerPlan?.file} color="claude">
          {dinners.length === 0 && <Text dimColor>No meal plan in plans/ yet.</Text>}
          {dinners.map(d => {
            const when = relativeDay(d.day, today)
            return (
              <Text wrap="truncate-end" dimColor={when === -1}>
                <Text color={when === 0 ? 'claude' : undefined} bold={when === 0}>
                  {when === 0 ? '▸ ' : '  '}
                  {d.day.padEnd(4)}
                </Text>
                <Text bold={when === 0}>{d.dish}</Text>
              </Text>
            )
          })}
        </Card>

        <Box marginTop={1}>
          <Card
            title="Basket"
            aside={storeName ?? undefined}
            color={view && view.unavailableCount > 0 ? 'error' : 'success'}
          >
            {error && <Text color="error" wrap="wrap">✗ {error}</Text>}
            {!view && !error && <Text dimColor>{loading ? 'Loading…' : 'No basket yet.'}</Text>}
            {view && lines.length === 0 && <Text dimColor>The basket is empty.</Text>}
            {shown.slice(0, room).map(line => (
              <Row
                color={line.isUnavailable ? 'error' : undefined}
                left={
                  <Text>
                    <Text dimColor={!line.isUnavailable}>{`${line.quantity}`.padStart(4)} × </Text>
                    {line.title}
                  </Text>
                }
                right={
                  <Text>
                    {line.isUnavailable ? <Text color="error" inverse> utsolgt </Text> : null}
                    {line.isOffer && !line.isUnavailable ? <Text color="success">tilbud </Text> : null}
                    {kroner(line.lineTotal).padStart(7)}
                  </Text>
                }
              />
            ))}
            {hidden > 0 && <Text dimColor>       … and {hidden} more</Text>}
            {view && lines.length > 0 && (
              <Box flexDirection="column" marginTop={1}>
                <Row
                  left={
                    <Text>
                      <Text bold>Total</Text>
                      <Text dimColor> · {lines.length} items</Text>
                    </Text>
                  }
                  right={<Text bold>{kroner(view.total)}</Text>}
                />
                {view.saved >= 1 || view.unavailableCount > 0 ? (
                  <Text>
                    {view.saved >= 1 ? <Text color="success">{kroner(view.saved)} saved on offers</Text> : null}
                    {view.saved >= 1 && view.unavailableCount > 0 ? <Text dimColor> · </Text> : null}
                    {view.unavailableCount > 0 ? (
                      <Text color="error">{view.unavailableCount} unavailable, run matlevering refresh</Text>
                    ) : null}
                  </Text>
                ) : null}
              </Box>
            )}
          </Card>
        </Box>
      </Box>
    )
  })
}
