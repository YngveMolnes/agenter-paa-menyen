"""Find the cheapest option per kg/litre for each item on a list.

uv run python examples/cheapest.py "kylling lårfilet" "laktosefri melk" havregryn
"""

import sys

from matlevering.auth import get_session
from matlevering.meny import Meny

queries = sys.argv[1:] or ["kylling lårfilet", "laktosefri melk", "havregryn"]
meny = Meny(*get_session())

for query in queries:
    # Search is fuzzy: keep products whose name has every word of the query,
    # and compare per kg or litre only (not per portion or piece).
    words = query.lower().split()
    hits = [
        p
        for p in meny.search(query, page_size=30)
        if p.get("isForSale", True)
        and not p.get("isOutOfStock")
        and p.get("compareUnit") in ("kg", "l")
        and all(w in f"{p['title']} {p.get('subtitle') or ''}".lower() for w in words)
    ]
    if not hits:
        print(f"{query}: nothing found")
        continue
    best = min(hits, key=lambda p: p["comparePricePerUnit"])
    print(
        f"{query}: {best['title']} {best.get('subtitle') or ''} "
        f"({best['ean']}), {best['pricePerUnit']:.2f} kr = "
        f"{best['comparePricePerUnit']:.2f} kr/{best['compareUnit']}"
    )
