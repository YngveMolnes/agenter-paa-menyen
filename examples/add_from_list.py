"""Put a shopping list into the basket, after checking it against your store.

Shows what would change by default. Add --apply to change the basket.

    uv run python examples/add_from_list.py examples/shopping-list.example.json
    uv run python examples/add_from_list.py examples/shopping-list.example.json --apply

The list is JSON: [{"ean": "...", "quantity": 2, "name": "optional"}, ...].
Quantities are set exactly (not added on top of what's already in the basket).
"""

import json
import sys
from pathlib import Path

from matlevering.auth import get_session
from matlevering.meny import Meny

args = [a for a in sys.argv[1:] if a != "--apply"]
apply = "--apply" in sys.argv
path = args[0] if args else "examples/shopping-list.example.json"

wanted = {item["ean"]: item["quantity"] for item in json.loads(Path(path).read_text())}
meny = Meny(*get_session())
print(f"Store: {meny.user_store().get('name', 'none set')}")

products = meny.products(list(wanted))
problems = [
    ean
    for ean in wanted
    if ean not in products
    or products[ean].get("isOutOfStock")
    or not products[ean].get("isForSale", True)
]
for ean in problems:
    print(f"  not available at your store: {ean}")

current = {item["ean"]: item["quantity"] for item in meny.active_items()}
changes = {
    ean: qty
    for ean, qty in wanted.items()
    if ean not in problems and current.get(ean) != qty
}
for ean, qty in changes.items():
    p = products[ean]
    print(
        f"  {current.get(ean, 0):g} -> {qty:g}  {p['title']} {p.get('subtitle') or ''}  ({p['pricePerUnit']:.2f} kr)"
    )

if not changes:
    print("Nothing to change.")
elif apply:
    meny.set_quantities(changes)
    print(f"Updated {len(changes)} item(s).")
else:
    print("Dry run. Add --apply to change the basket.")
