"""Put a shopping list into the basket, after checking it against your store.

Shows what would change by default. Add --apply to change the basket.

    uv run python examples/add_from_list.py examples/shopping-list.example.json
    uv run python examples/add_from_list.py examples/shopping-list.example.json --apply

The list is JSON: [{"ean": "...", "quantity": 2, "name": "optional"}, ...].
Quantities are set exactly (not added on top of what's already in the basket).
"""

import json
import math
import sys
from pathlib import Path

from matlevering.auth import get_session
from matlevering.meny import Meny

args = [a for a in sys.argv[1:] if a != "--apply"]
apply = "--apply" in sys.argv
path = args[0] if args else "examples/shopping-list.example.json"

wanted = {item["ean"]: item["quantity"] for item in json.loads(Path(path).read_text())}
for ean, qty in wanted.items():
    if type(qty) not in (int, float) or not math.isfinite(qty) or qty < 0:
        sys.exit(f"Expected a finite, nonnegative quantity for {ean}.")

# Read the profile once so the named store and the catalog use the same GLN.
meny = Meny(*get_session(), store_gln="0")
positive = [ean for ean, qty in wanted.items() if qty > 0]
products = {}
if positive:
    store = meny.user_store()
    if not store:
        sys.exit("Choose a store on meny.no before checking positive quantities.")
    meny.store_gln = store["gln"]
    print(f"Store: {store.get('name') or meny.store_gln}")
    products = meny.products(positive)

current = {item["ean"]: item for item in meny.active_items()}
changes = {}
for ean, qty in wanted.items():
    item = current.get(ean, {})
    before = item.get("quantity", 0)
    if qty > 0:
        product = products.get(ean)
        if not product or Meny.unavailable({"product": product}):
            print(f"  not available at your store: {ean}")
            continue
    if before == qty:
        continue
    changes[ean] = qty
    if qty == 0:
        title = (item.get("product") or {}).get("title") or ean
        print(f"  {before:g} -> 0  {title}")
    else:
        print(
            f"  {before:g} -> {qty:g}  {product['title']} {product.get('subtitle') or ''}  ({product['pricePerUnit']:.2f} kr)"
        )

if not changes:
    print("Nothing to change.")
elif apply:
    meny.set_quantities(changes)
    print(f"Updated {len(changes)} item(s).")
else:
    print("Dry run. Add --apply to change the basket.")
