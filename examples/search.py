"""Search your store and show price per unit and offers.

uv run python examples/search.py laktosefri kesam
"""

import sys

from matlevering.auth import get_session
from matlevering.meny import Meny

query = " ".join(sys.argv[1:]) or "kyllingfilet"
meny = Meny(*get_session())

for p in meny.search(query, page_size=10):
    if p.get("isOutOfStock") or not p.get("isForSale", True):
        continue
    offer = (
        f"  (offer, normally {p['pricePerUnitOriginal']:.2f})"
        if p.get("isOffer")
        else ""
    )
    unit_price = (
        f"{p['comparePricePerUnit']:.2f} kr/{p['compareUnit']}"
        if p.get("compareUnit")
        else ""
    )
    print(f"{p['ean']:>13}  {p['title']} {p.get('subtitle') or ''}")
    print(f"{'':>13}  {p['pricePerUnit']:.2f} kr  {unit_price}{offer}")
