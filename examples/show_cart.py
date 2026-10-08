"""Show the basket grouped by category, with unavailable items and offers called out.

uv run python examples/show_cart.py
"""

from collections import defaultdict

from matlevering.auth import get_session
from matlevering.meny import Meny

meny = Meny(*get_session())
store = meny.user_store()
print(f"Store: {store.get('name', 'none set')}\n")

by_category = defaultdict(list)
for item in meny.active_items():
    by_category[(item.get("product") or {}).get("categoryName") or "Other"].append(item)

total = 0.0
for category, items in sorted(by_category.items()):
    print(category)
    for item in items:
        p = item.get("product") or {}
        line = item["pricePerUnit"] * item["quantity"]
        total += line
        notes = []
        if Meny.unavailable(item):
            notes.append("UNAVAILABLE at your store")
        if p.get("isOffer"):
            notes.append(f"offer, normally {p['pricePerUnitOriginal']:.2f}")
        note = f"  [{'; '.join(notes)}]" if notes else ""
        print(
            f"  {item['quantity']:>5g} x {p.get('title', '?')} {p.get('subtitle') or ''}  {line:.2f} kr{note}"
        )

print(f"\nTotal at list prices: {total:.2f} kr")
