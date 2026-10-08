import { expect, test } from 'claude-code/testing'

import { kroner, parseDinners, summarizeCart } from '../hooks/parse'

const PLAN = `# Plan

## 4. Something else
| Day | Not this |
|---|---|
| Mon | wrong table |

## 5. Dinner lineup (shared base, different portions)

| Day | Dinner | Fish? | Active / total |
|---|---|---|---|
| Mon | **Chicken curry** with rice | – | 25 / 45 min |
| Tue | **Fresh salmon fillet** with white rice | **Salmon** | 15 / 40 min |

Fish: salmon once.

## 6. Sunday prep
| Sun | not a dinner |
`

test('reads the dinner table under the dinner heading only', () => {
  expect(parseDinners(PLAN)).toEqual([
    { day: 'Mon', dish: 'Chicken curry with rice' },
    { day: 'Tue', dish: 'Fresh salmon fillet with white rice' },
  ])
  expect(parseDinners('# no plan here')).toEqual([])
})

test('summarises the basket and flags what the website shows as sold out', () => {
  const cart = JSON.stringify({
    items: [
      { ean: '1', quantity: 2, pricePerUnit: 23.9, product: { title: 'Lettmelk', subtitle: '1l' } },
      { ean: '2', quantity: 1, pricePerUnit: 28.9, doesNotExistInCurrentStore: true, product: { title: 'Epler' } },
      { ean: '3', quantity: 1, pricePerUnit: 10, product: { title: 'Gone', isOutOfStock: true } },
      { ean: '4', quantity: 5, pricePerUnit: 99, __removed__: true, product: { title: 'Removed' } },
      { ean: '5', quantity: 1, pricePerUnit: 69.9, product: { title: 'Kjøttdeig', isOffer: true } },
    ],
  })
  const view = summarizeCart(cart)

  expect(view.lines.map(line => line.ean)).toEqual(['1', '2', '3', '5'])
  expect(view.lines[0]?.title).toBe('Lettmelk 1l')
  expect(view.unavailableCount).toBe(2)
  expect(view.lines[3]?.isOffer).toBe(true)
  expect(Math.round(view.total * 100)).toBe(Math.round((47.8 + 28.9 + 10 + 69.9) * 100))
})

test('formats kroner with thin grouping', () => {
  expect(kroner(2121.28)).toBe('2 121 kr')
  expect(kroner(47.8)).toBe('48 kr')
})
