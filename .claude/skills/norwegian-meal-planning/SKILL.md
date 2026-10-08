---
name: norwegian-meal-planning
description: Plan meals, recipes and a priced grocery list for a Norwegian household, and fill the user's meny.no basket with this repo's `matlevering` CLI. Use when the user asks for a meal plan, ukesmeny, middagsplan, handleliste, a food budget, or to fill or fix their MENY basket.
---

# Norwegian meal planning with `matlevering`

This skill turns a household's needs into a meal plan for some days, a shopping list with real
MENY products and prices, and (only when asked) a filled meny.no basket. Calories, protein and
costs are estimates; say so in the plan.

## 0. The store comes first. Tell the user explicitly.

Before any search or price check, tell the user **in plain words**:

> Set the correct store in your Trumf/MENY account first: on meny.no, choose your store in the
> webshop's store picker ("Velg butikk"). I read the store from your profile, and the range,
> stock and prices are different in every MENY store.

Then run `uv run matlevering store` and ask the user to confirm that the name and address are
their store. Don't continue until they have confirmed it.

Why this matters (learned the hard way):
- Search without a store (store `0`) shows the whole chain's range. A plan checked like that put
  many items in the basket that the user's store doesn't sell, and the website showed
  "Midlertidig utsolgt" on them.
- The website decides "Midlertidig utsolgt" from the product snapshot **stored in each basket
  item**: `doesNotExistInCurrentStore`, `product.isOutOfStock`, `product.isForSale` and
  `product.availableInventory`. Those flags stay stale after a store change. Run
  `uv run matlevering refresh` after the store changes, and before telling the user the basket is
  ready.
- Store GLNs, MENY's store IDs, are 13-digit numbers starting with `7080001`. The client reads the store from the
  profile, so you don't need to pass a GLN.

## 1. Ask before planning (one round, then sensible defaults)

Ask about everything below that the user hasn't told you. Write down the answers and the
assumptions you made at the top of the plan.

- **Who eats and when:** number of adults and children, and which days the plan covers. A common
  setup is weekdays only, with weekends and extra shopping trips "freestyle" outside the plan.
  Leave small children out of the calorie maths unless asked.
- **Per person:** calorie target, weight (for protein), protein goal, and meal pattern. Patterns
  seen in practice:
  - Intermittent fasting with two meals: one before the gym and one after.
  - OMAD (one meal a day) on rest days. Make it a starter, a big main and a dessert bowl, because
    2000 kcal in one plate is hard to eat.
  - Ask for the training days by weekday.
- **Breastfeeding, pregnancy, health:**
  - Breastfeeding adds roughly 330–500 kcal a day. 2000 kcal is often too low; land around
    2200–2400 with gentle loss at most, because cutting hard can hurt milk supply and worsen
    cravings.
  - Give her regular meals and planned snacks (no fasting), plus a planned evening "craving slot"
    (dark chocolate, dates, a kesam bowl) instead of pretending cravings won't happen.
  - Refer low milk supply, supplements and herbal "milk boosters" to helsestasjon, jordmor or the
    GP. Be honest that the evidence for oats or other "galactagogue" foods is weak.
  - Pregnancy: refer food-safety questions (liver, raw fish, listeria) to jordmor; don't improvise.
- **Intolerances and allergies:**
  - Lactose: use "Laktosefri" dairy (Tine has milk, kesam, cottage cheese, rømme, crème fraîche).
    Hard cheeses and butter are usually tolerated, but ask.
  - For shared dishes, buy one set of lactose-free dairy for everyone. It covers calcium and
    iodine just as well.
  - Check the product's `allergens` field (codes: `JA` contains, `KAN` may contain, `FRI` free,
    `UKJ` unknown). Example: some leverpostei brands contain milk and others don't.
- **Dislikes and quality bars:** ask explicitly, and don't assume cheapest = acceptable. Things
  users rejected during planning:
  - Cheap frozen salmon ("rough"): good fresh salmon less often is better.
  - Wholegrain pasta.
  - Canned mackerel.
  - Fish in tacos (mince was preferred, and the fish was poor value there).
  - Trout as a salmon stand-in.
- **Budget:** a monthly food budget, and what it must also cover (unplanned days, extra trips,
  children, household items).
  - Weekly budget = monthly / 4.33. Give the planned days a share and leave a margin for the rest.
  - SIFO's referansebudsjett is a useful reference for what's normal.

## 2. Norwegian nutrition basics to build in

- **Fish:** Helsedirektoratet advises fish for dinner 2–3 times a week, at least half of it fatty
  fish (salmon, trout, mackerel, herring). If the household rejects fish, say that the plan falls
  short and suggest asking helsestasjon or the GP about tran or omega-3 (especially when
  breastfeeding).
- **Vitamin D** in winter (supplement or tran). **Iodine** from milk, dairy, fish and eggs. This
  matters when breastfeeding, and lactose-free dairy works just as well.
- **Breastfeeding:** no alcohol, caffeine at most ~200 mg a day, no high-mercury fish (swordfish,
  shark, large tuna, pike). Farmed salmon is low in mercury.
- **Fullness:** high protein, high fibre and volume (vegetables, potatoes, rice, oats, legumes).

## 3. Making it affordable without making it worse

- **Biggest cost drivers:** meat and fish fillets, lactose-free dairy, organic berries and premium
  brands.
- **Cheaper protein:**
  - Chicken thighs instead of fillet.
  - Karbonadedeig 5% (lean minced pork).
  - Eggs, kesam and cottage cheese.
  - Red lentils and beans to stretch curry and chili.
- **Store brands:** First Price is cheapest, then Eldorado and MENY's own brand. Vilje is organic
  and costs more.
- **One quality highlight** (e.g. fresh salmon fillet cut in store, ~340 kr/kg, or loin, 450+
  kr/kg) beats cheap versions several times.
- **Batch cooking:** a Sunday curry and a midweek chili of ~8 portions each. Leftovers become
  lunches and pre-gym meals; 2 portions go in the freezer for bad days.
- **Shared dinners:** the same dish for everyone, with different portion sizes per person.
- **Show two cost figures:** the cost of the planned days (the share actually eaten) and the list
  total including stock-up (staples that last beyond the period).
- **Offers:** flag items that are only cheap because of an offer (`isOffer`,
  `pricePerUnitOriginal`), and say what the week costs at full price.

## 4. Using the CLI

```sh
uv run matlevering store                 # the store on the user's profile
uv run matlevering search kyllingfilet -n 10
uv run matlevering cart                  # flags [UNAVAILABLE] items
uv run matlevering add <ean> [qty]
uv run matlevering set <ean> <qty>       # 0 removes
uv run matlevering remove <ean>
uv run matlevering refresh               # re-sync snapshots and prices with the store
uv run matlevering clear
```

From Python (`from matlevering.auth import get_session; from matlevering.meny import Meny`):
- `Meny(*get_session())` uses the profile's store.
- `.products([eans])` returns full product data, including `isOffer`, `pricePerUnitOriginal`,
  `allergens`, `productSoldByWeight`, `unitRule` and `isOutOfStock`.
- `.set_quantities({ean: qty})` adds or changes many items in one request.

**Notes:**
- **Search in Norwegian:** "laktosefri kesam", "kylling lårfilet", "karbonadedeig", "laks loin",
  "frosne bær".
- **Weighed items ("pr Kg"):** the quantity is kg as a decimal in steps of `unitRule` (often
  0.15), e.g. 0.45. Loose produce has short codes (bananas `4011`, cucumber `4595`, lemon `4033`).
- **Validate every item at the user's store** before adding it (it exists, is in stock, and the
  price is current), and again after adding. Replace anything missing with the closest match from
  the same store.
- **Rules for the basket:**
  - Only change the basket when the user asks.
  - Never check out: the user picks a delivery slot and pays on meny.no.
  - Never run `login` yourself or read `.env`, because the user's password is involved. Ask the
    user to run `! uv run matlevering login` (and `--otp <code>` if Trumf sends an SMS).
- **If the session has expired**, any command says "run `matlevering login`"; ask the user to do it.
- **The pane mod:** if the user started Claude Code with `--plugin-dir mods/matlevering`, the
  Matlevering pane shows the basket and the plan's dinner lineup and refreshes itself. Tell them
  `/meny` opens it. Keep the plan's dinner section as a `## ... Dinner ...` heading over a
  `| Day | Dinner | ... |` table, because that's what the pane reads.

## 5. Deliverables

- `plans/meal-plan-<period>.md`:
  - Assumptions, targets and the reasoning behind them.
  - A day-by-day table per person, with kcal and protein per meal and per day.
  - The dinner lineup and a batch-prep plan.
  - Recipes with amounts, the split per person, and hands-on/total time.
  - A craving strategy if relevant.
  - The shopping table and the two cost figures.
  - Name the store the list was checked against.
- `plans/shopping-list.json`: a list of
  `{"ean", "name", "quantity", "unit_price", "used_for"}`. `quantity` is the number of packs, or
  kg for weighed items. Only use EANs that came from the tool.

Keep both files in sync whenever the user swaps something, and re-check the totals.

## 6. Workflow

1. Give the store warning (section 0), run `matlevering store`, and get the user's confirmation.
2. Ask the questions in section 1.
3. Draft the plan and price it with `search` and `products` at that store.
4. Validate the whole list: it exists at the store, is in stock, prices are current, and offers
   are flagged.
5. Summarise briefly (targets, dinners, cost, caveats). Iterate on the user's swaps, updating both
   files each time.
6. When asked, fill the basket from the JSON with `set_quantities`, run `refresh`, and check that
   `cart` shows no `[UNAVAILABLE]` items. Remind the user to choose a delivery slot and check out
   on meny.no themselves.
