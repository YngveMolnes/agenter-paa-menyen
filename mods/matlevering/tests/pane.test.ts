import { expect, test } from 'claude-code/testing'

const PLAN = `## 5. Dinner lineup

| Day | Dinner |
|---|---|
| Mon | **Chicken curry** with rice |
| Tue | **Fresh salmon fillet** with white rice |
`

const CART = JSON.stringify({
  items: [
    {
      ean: '1',
      quantity: 2,
      pricePerUnit: 23.9,
      product: { title: 'Lettmelk', subtitle: '1l', isOffer: true, pricePerUnitOriginal: 33.9 },
    },
    { ean: '2', quantity: 1, pricePerUnit: 28.9, doesNotExistInCurrentStore: true, product: { title: 'Epler 1kg' } },
  ],
})

for (const surface of ['terminal', 'desktop'] as const) {
  test(`draws dinners and basket on ${surface}`, async ($, on) => {
    // Stand in for the repo, the CLI and the host beneath the mod.
    on('fs.exists', () => ({ value: true }))
    on('fs.list', () => ({
      value: [{ name: 'meal-plan-5-days.md', kind: 'file' as const, size: 1, mtimeMs: 1, isLink: false }],
    }))
    on('fs.read', () => ({ value: PLAN }))
    on('process.run', (_, e) => ({
      value: {
        exitCode: 0,
        stdout: e.argv.includes('--json') ? CART : 'MENY Eksempel, Storgata 1 0001 Oslo\nGLN 1\n',
        stderr: '',
        isStdoutTruncated: false,
        isStderrTruncated: false,
      },
    }))
    on('command.register', (_, e) => ({ value: { command: e.name } }))
    on('ui.open', () => ({ value: { isPlaced: true as const } }))
    on('ui.status', () => ({ value: undefined }))
    on('clock.every', () => ({ value: undefined }))
    on('session.start', (_, e) => ({ cwd: e.cwd }))

    await $.session.start({ cwd: '/repo', surface, isInteractive: true })

    const ui = await $.ui.mount({
      plugin: 'matlevering',
      surface,
      component: 'Pane',
      requestId: 'matlevering',
      props: {
        title: 'Matlevering',
        isFocused: false,
        bodyColumns: 80,
        placement: 'dock',
        scroll: { offset: 0, bodyRows: 30 },
        view: {},
      },
      viewport: { columns: 80, rows: 30 },
    })
    const drawn = JSON.stringify(await ui.drawn())

    for (const text of [
      'Dinners',
      'Chicken curry with rice',
      'Basket',
      'MENY Eksempel',
      'Lettmelk 1l',
      'utsolgt',
      'tilbud',
      '77 kr',
      '20 kr',
      ' saved on offers',
      ' unavailable, run matlevering refresh',
    ]) {
      expect(drawn).toContain(text)
    }
  })
}

test('a failed basket refresh keeps the previous basket and success time', async ($, on) => {
  let basket = CART
  let failure = 'No initial basket'
  let planFailed = false
  const written: Record<string, unknown> = {}
  let successTimes = 0
  on('state.set', async (_, e, next) => {
    const result = await next(e)
    written[e.key] = e.value
    if (e.key === 'updatedAt') successTimes++
    return result
  })
  on('fs.exists', () => ({ value: true }))
  on('fs.list', () => {
    if (planFailed) throw new Error('Fixture plan unavailable')
    return { value: [] }
  })
  on('process.run', (_, e) => ({
    value: {
      exitCode: e.argv.includes('--json') && failure ? 1 : 0,
      stdout: e.argv.includes('--json') ? basket : 'MENY Eksempel\nGLN 1\n',
      stderr: failure,
      isStdoutTruncated: false,
      isStderrTruncated: false,
    },
  }))
  on('command.register', (_, e) => ({ value: { command: e.name } }))
  on('ui.open', () => ({ value: { isPlaced: true as const } }))
  on('ui.status', () => ({ value: undefined }))
  on('clock.every', () => ({ value: undefined }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  expect((await $.command.run({ command: 'meny' })).text).toContain('Basket refresh failed. No initial basket')
  expect(successTimes).toBe(0)
  failure = ''
  expect((await $.command.run({ command: 'meny' })).text).toContain('77 kr')
  const at = written.updatedAt
  const previousBasket = written.cart
  const successes = successTimes
  expect(typeof at).toBe('number')
  failure = 'Fixture basket unavailable'
  expect((await $.command.run({ command: 'meny' })).text).toContain('Basket refresh failed. Fixture basket unavailable')
  expect(written.updatedAt).toEqual(at)
  expect(written.cart).toEqual(previousBasket)

  failure = ''
  for (basket of ['{}', '{"items":[{"quantity":1}]}', '{']) {
    expect((await $.command.run({ command: 'meny' })).text).toContain('Basket refresh failed')
    expect(written.cart).toEqual(previousBasket)
    expect(successTimes).toBe(successes)
  }
  basket = JSON.stringify({ items: [] })
  planFailed = true
  const partial = await $.command.run({ command: 'meny' })
  expect(partial.text).toContain('0 items, 0 kr')
  expect(partial.text).toContain('Dinner plan refresh failed')
  expect(written.cartError).toBe(null)
  expect(successTimes).toBe(successes + 1)
})

function signal() {
  let resolve!: () => void
  const promise = new Promise<void>(done => { resolve = done })
  return { promise, resolve }
}

test('a command during a refresh waits for a new basket read', async ($, on) => {
  const reading = signal()
  const release = signal()
  const opened = signal()
  let opens = 0
  let basketReads = 0
  on('fs.exists', () => ({ value: true }))
  on('fs.list', () => ({ value: [] }))
  on('process.run', async (_, e) => {
    let stdout = 'MENY Eksempel'
    let stderr = ''
    if (e.argv.includes('--json')) {
      if (++basketReads === 1) {
        reading.resolve()
        await release.promise
        stdout = CART
      } else {
        stderr = 'The requested read failed'
      }
    }
    return { value: { exitCode: stderr ? 1 : 0, stdout, stderr, isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('command.register', (_, e) => ({ value: { command: e.name } }))
  on('ui.open', () => {
    if (++opens === 2) opened.resolve()
    return { value: { isPlaced: true as const } }
  })
  on('ui.status', () => ({ value: undefined }))
  on('clock.every', () => ({ value: undefined }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  await reading.promise
  const command = $.command.run({ command: 'meny' })
  await opened.promise
  release.resolve()
  expect((await command).text).toContain('Basket refresh failed. The requested read failed')
  expect(basketReads).toBe(2)
})

test('a plan-only edit leaves the basket state and its timestamp alone', async ($, on) => {
  const planUpdated = signal()
  let basketReads = 0
  let successTimes = 0
  let planText = PLAN
  let lastPlan = ''
  let changed = false
  on('state.set', async (_, e, next) => {
    const result = await next(e)
    if (e.key === 'updatedAt') successTimes++
    if (e.key === 'plan') lastPlan = JSON.stringify(e.value)
    if (changed && e.key === 'isLoading' && e.value === false) planUpdated.resolve()
    return result
  })
  on('fs.exists', () => ({ value: true }))
  on('fs.list', () => ({ value: [{ name: 'meal-plan.md', kind: 'file' as const, size: 1, mtimeMs: 1, isLink: false }] }))
  on('fs.read', () => ({ value: planText }))
  on('process.run', (_, e) => {
    if (e.argv.includes('--json')) basketReads++
    return { value: { exitCode: 0, stdout: e.argv.includes('--json') ? CART : 'MENY Eksempel',
      stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('command.register', (_, e) => ({ value: { command: e.name } }))
  on('ui.open', () => ({ value: { isPlaced: true as const } }))
  on('ui.status', () => ({ value: undefined }))
  on('clock.every', () => ({ value: undefined }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('tool.call', { tool: 'Write' }, () => ({ result: 'written' }))

  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'meny' })
  const initialReads = basketReads
  const initialTimes = successTimes
  changed = true
  planText = PLAN.replace('Chicken curry', 'Vegetable curry')
  await $.tool.call({ tool: 'Write', file_path: 'plans/meal-plan.md', content: planText })
  await planUpdated.promise
  expect(lastPlan).toContain('Vegetable curry')
  expect(basketReads).toBe(initialReads)
  expect(successTimes).toBe(initialTimes)
})
