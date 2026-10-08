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
