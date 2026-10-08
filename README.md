# matlevering

Control your meny.no basket from Python: search products, add and remove items, and re-sync the
basket with your store. It comes with an agent skill that plans meals for a Norwegian household
and fills the basket from the plan.

It uses meny.no's own (unofficial) web API, reverse-engineered from the website. It can break when
MENY changes their site. It never checks out: you choose a delivery slot and pay on meny.no.

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python 3.13 is installed for you)
- A Trumf account with a mobile number. MENY logs in through Trumf ID, using the **phone number**,
  not the email address.

## Setup

```sh
uv sync
cp .env.example .env    # fill in TRUMF_USERNAME (mobile number) and TRUMF_PASSWORD
uv run matlevering login
uv run matlevering login --otp 123456   # only if Trumf sent an SMS code
```

The session is saved in `.session/` (git-ignored), so later commands don't log in again. When the
session expires, run `login` again. Trumf usually remembers the device, so it rarely asks for an SMS
code after the first time.

Optional: to see the basket and the week's dinners in a pane while you work with Claude Code, start
it with the mod loaded (see [Claude Code mod](#claude-code-mod-basket-and-dinners-pane)):

```sh
claude --plugin-dir mods/matlevering
```

## Choose your store first

**Set the correct store in your Trumf/MENY account on meny.no** (the store picker in the webshop,
"Velg butikk"). The tool reads the store from your profile, and range, stock and prices are
different in every MENY store. Check which store it uses:

```sh
uv run matlevering store
```

If you change store later, run `uv run matlevering refresh`. Otherwise the basket keeps product
data from the old store, and meny.no may show items as "Midlertidig utsolgt" even though your new
store has them.

## Usage

```sh
uv run matlevering search lettmelk          # EAN, name, price at your store
uv run matlevering cart                     # items marked [UNAVAILABLE] won't be delivered
uv run matlevering add 7048840000029 2      # adds to what's already there
uv run matlevering set 7048840000029 1      # exact quantity; 0 removes
uv run matlevering remove 7048840000029
uv run matlevering refresh                  # re-sync products and prices with your store
uv run matlevering clear
uv run matlevering token                    # print an access token for your own scripts
```

From Python:

```python
from matlevering.auth import get_session
from matlevering.meny import Meny

meny = Meny(*get_session())                   # uses the store on your profile
meny.search("kesam laktosefri")
meny.set_quantities({"7048840000029": 2, "7038010009457": 1})
```

## Examples

Small scripts in `examples/`. They all use your saved session and the store on your profile.

```sh
uv run python examples/search.py laktosefri kesam            # results with kr/kg and offers
uv run python examples/cheapest.py "kylling lårfilet" kesam   # cheapest per kg/l for each item
uv run python examples/show_cart.py                           # basket by category, unavailable items flagged
uv run python examples/add_from_list.py examples/shopping-list.example.json          # dry run
uv run python examples/add_from_list.py examples/shopping-list.example.json --apply  # change the basket
```

`add_from_list.py` checks every product against your store, then sets the quantities from the list
(so 6 bananas means 6 in the basket, not 6 more). It only changes the basket with `--apply`.

## Claude Code mod: basket and dinners pane

`mods/matlevering/` is a [Claude Code mod](https://claude.com/resources/articles/claude-code-mods)
that adds a **Matlevering** pane:

- **Dinners:** the dinner lineup from the newest `plans/meal-plan-*.md`, with today's dinner
  highlighted and past days dimmed.
- **Basket:** your MENY basket with the store name, each line's price and the total. Unavailable
  items ("utsolgt") come first in red, offers are marked "tilbud", and the footer shows how much
  the offers save.

Load it when you start Claude Code in this repo:

```sh
claude --plugin-dir mods/matlevering
```

It switches on only inside this repo and refreshes the basket after any `matlevering` command, and
every 5 minutes. The dinners refresh when a meal plan is written. `/meny` opens the pane and
refreshes both. The pane opens by itself on terminals at least 144 columns wide; `/meny` opens it
at any width. The status line shows "Basket: N items, X kr".

Tests: `claude plugin test mods/matlevering`.

## Meal planning with an agent

`.claude/skills/norwegian-meal-planning/` is a Claude Code skill. It plans meals, recipes and a
priced shopping list for a Norwegian household and can fill the basket from it. It covers:

- Calorie and protein targets: fasting/OMAD patterns, breastfeeding, gym days.
- Lactose-free dairy and allergens.
- Norwegian fish and vitamin advice.
- Budget levers.
- Checking every item at your store before it goes in the basket.

Ask for something like "plan dinners for next week for two adults, budget 2,000 kr". The plan is
written to `plans/meal-plan-*.md`, and a machine-readable list to `plans/shopping-list.json`.

### Setup prompt for an agent

Paste this into a new Claude Code (or other coding agent) session in this directory:

```text
Set up the matlevering repo in this directory so I can manage my meny.no basket from here.

1. Check that uv is installed (`uv --version`). If it isn't, tell me how to install it and stop.
2. Run `uv sync`.
3. If there is no `.env`, copy `.env.example` to `.env` and ask me to fill in TRUMF_USERNAME (my
   mobile number, not my email) and TRUMF_PASSWORD myself. Don't read, print or edit `.env`.
4. Ask me to log in myself by running `! uv run matlevering login`. If it says an SMS code was
   sent, ask me to run `! uv run matlevering login --otp <code>`. Never enter my password or run
   the login for me.
5. Tell me explicitly to set the correct store in my Trumf/MENY account on meny.no ("Velg
   butikk"), because range, stock and prices differ per store. Then run `uv run matlevering store`
   and ask me to confirm that it's my store.
6. Run `uv run matlevering cart` to show that everything works, and summarise what's in my basket.
7. Run `claude plugin test mods/matlevering` to check the Matlevering pane mod. Then tell me to
   restart Claude Code with `claude --plugin-dir mods/matlevering` to get the pane with my basket
   and dinners, and that `/meny` opens and refreshes it.

For meal planning, use the norwegian-meal-planning skill in `.claude/skills/`. Don't change my
basket unless I ask, and never try to check out.
```

## How it works

- **Login:** Trumf ID (OpenID Connect) through meny.no's own login. The script handles the phone
  number, password, SMS code, "register biometrics" and "continue as" steps, then gets an access
  token from meny.no. See `src/matlevering/auth.py`.
- **Basket and products:** `platform-rest-prod.ngdata.no`, NorgesGruppen's shared webshop API.
  See `src/matlevering/meny.py`.
- **API notes:** endpoints, request formats and the verified basket behaviour are in
  `docs/meny-api.md`.
- **User-Agent:** requests send a normal browser User-Agent with `agenter-paa-menyen/0.1` at the
  end, so MENY can see what is making them (`CLIENT_NAME` in `src/matlevering/auth.py`).

## License

MIT, see [LICENSE](LICENSE). This project is not affiliated with MENY, NorgesGruppen or Trumf.
