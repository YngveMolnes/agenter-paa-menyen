"""Client for the meny.no webshop API (NorgesGruppen platform-rest).

Cart semantics, verified against the live API (see docs/meny-api.md):
- PUT /api/client-list-sync/{chain}/cart merges per item: items in the body
  are upserted, items left out are untouched.
- An item is removed by sending it with `__removed__: true`; the server keeps
  it as a tombstone. Each change bumps the item's `__rev__`.
- DELETE clears the whole cart.
"""

import copy
import uuid
from datetime import UTC, datetime

import requests

PLATFORM_REST = "https://platform-rest-prod.ngdata.no"
CHAIN_ID = "1300"  # MENY


def api_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "FWC-Chain-Id": CHAIN_ID,
        "FWC-Using-Bearer-Token": "true",
        "FWC-Using-Api-key": "false",
    }


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _empty_cart() -> dict:
    return {
        "__id__": "cart",
        "__rev__": 1,
        "__removed__": False,
        "__type__": "CART",
        "title": "cart",
        "items": [],
    }


class Meny:
    def __init__(
        self, session: requests.Session, token: str, store_gln: str | None = None
    ):
        self.s = session
        self.headers = api_headers(token)
        # Assortment and stock differ per store; default to the user's chosen
        # store, falling back to "0" (chain-wide) when none is set.
        self.store_gln = store_gln or self.user_store().get("gln") or "0"
        # Product search returns nothing for a logged-in user without a chosen
        # store, so it runs without the user token.
        self.anon = requests.Session()
        self.anon.headers.update(
            {"FWC-Chain-Id": CHAIN_ID, "User-Agent": session.headers["User-Agent"]}
        )

    def user_store(self) -> dict:
        """The store chosen on the user's profile ({} if none)."""
        r = self.s.get(
            f"{PLATFORM_REST}/api/extended-user/{CHAIN_ID}",
            headers={**self.headers, "x-fw-core-fetch-data": "true"},
            timeout=30,
        )
        r.raise_for_status()
        store = r.json().get("store") or {}
        return store if store.get("gln") not in (None, "", "0") else {}

    @property
    def _cart_url(self) -> str:
        return f"{PLATFORM_REST}/api/client-list-sync/{CHAIN_ID}/cart"

    # Products

    def search(self, query: str, page_size: int = 10) -> list[dict]:
        r = self.anon.get(
            f"{PLATFORM_REST}/api/products/{CHAIN_ID}/{self.store_gln}",
            params={
                "search": query,
                "page": 1,
                "page_size": page_size,
                "fieldset": "maximal",
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["hits"]

    def products(self, eans: list[str]) -> dict[str, dict]:
        found = {}
        # The endpoint pages its results, so ask for a full page per batch.
        for start in range(0, len(eans), 50):
            batch = eans[start : start + 50]
            r = self.anon.get(
                f"{PLATFORM_REST}/api/products/{CHAIN_ID}/{self.store_gln}",
                params={
                    "product_ids": ",".join(batch),
                    "fieldset": "maximal",
                    "page_size": len(batch),
                },
                timeout=30,
            )
            r.raise_for_status()
            found.update({p["ean"]: p for p in r.json()["hits"]})
        return found

    # Cart

    def get_cart(self) -> dict:
        r = self.s.get(self._cart_url, headers=self.headers, timeout=30)
        if r.status_code == 404:  # "Cart not found": the user never had one
            return _empty_cart()
        r.raise_for_status()
        return r.json()

    def active_items(self, cart: dict | None = None) -> list[dict]:
        cart = cart if cart is not None else self.get_cart()
        return [i for i in cart["items"] if not i.get("__removed__")]

    def _put(self, cart: dict, items: list[dict]) -> dict:
        body = {
            **{k: v for k, v in cart.items() if k != "items"},
            "__clientId__": cart.get("__clientId__") or str(uuid.uuid4()),
            "__listRef__": str(uuid.uuid4()),
            "persistedId": cart.get("persistedId") or str(uuid.uuid4()),
            "items": items,
        }
        r = self.s.put(self._cart_url, json=body, headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _new_item(product: dict, quantity: float) -> dict:
        return {
            "id": product["ean"],
            "ean": product["ean"],
            "addedTime": _now(),
            "hasBeenSynced": False,
            "__rev__": 1,
            "__removed__": False,
            "__type__": "CART_PRODUCT",
            "quantity": quantity,
            "pricePerUnit": product["pricePerUnit"],
            "linePrice": product["pricePerUnit"] * quantity,
            "comparePricePerUnit": product["comparePricePerUnit"],
            "totalDiscount": 0,
            "linePriceAfterDiscount": None,
            "product": product,
            "doesNotExistInCurrentStore": False,
            "substitute": True,
            "shouldSlice": False,
        }

    def set_quantities(self, quantities: dict[str, float]) -> dict:
        """Set the quantity of each EAN; 0 removes it. Other items are left alone."""
        cart = self.get_cart()
        existing = {i["ean"]: i for i in cart["items"]}
        missing = [
            ean for ean, q in quantities.items() if q > 0 and ean not in existing
        ]
        found = self.products(missing) if missing else {}
        if unknown := [ean for ean in missing if ean not in found]:
            raise ValueError(f"Unknown EAN(s): {', '.join(unknown)}")

        changed = []
        for ean, quantity in quantities.items():
            item = existing.get(ean)
            if item is None:
                if quantity > 0:
                    changed.append(self._new_item(found[ean], quantity))
                continue
            item = copy.deepcopy(item)
            item["__rev__"] = item.get("__rev__", 1) + 1
            if quantity > 0:
                if item.get("__removed__"):
                    item["addedTime"] = _now()
                item["__removed__"] = False
                item["quantity"] = quantity
                item["linePrice"] = item["pricePerUnit"] * quantity
            else:
                item["__removed__"] = True
            changed.append(item)
        return self._put(cart, changed) if changed else cart

    def add(self, ean: str, quantity: float = 1) -> dict:
        current = {i["ean"]: i["quantity"] for i in self.active_items()}
        return self.set_quantities({ean: current.get(ean, 0) + quantity})

    def remove(self, ean: str) -> dict:
        return self.set_quantities({ean: 0})

    def refresh(self) -> dict:
        """Re-sync each item's product snapshot and price with the current store.

        The website decides "Midlertidig utsolgt" from the snapshot stored in
        the cart (and its doesNotExistInCurrentStore flag), so this clears stale
        flags after a store change and flags items the store doesn't sell.
        """
        cart = self.get_cart()
        items = [i for i in cart["items"] if not i.get("__removed__")]
        found = self.products([i["ean"] for i in items])
        changed = []
        for item in items:
            item = copy.deepcopy(item)
            item["__rev__"] = item.get("__rev__", 1) + 1
            product = found.get(item["ean"])
            item["doesNotExistInCurrentStore"] = product is None
            if product:
                item["product"] = product
                item["pricePerUnit"] = product["pricePerUnit"]
                item["comparePricePerUnit"] = product["comparePricePerUnit"]
                item["linePrice"] = product["pricePerUnit"] * item["quantity"]
            changed.append(item)
        return self._put(cart, changed) if changed else cart

    @staticmethod
    def unavailable(item: dict) -> bool:
        """Whether the website would show this item as unavailable."""
        p = item.get("product") or {}
        return bool(
            item.get("doesNotExistInCurrentStore")
            or p.get("isOutOfStock")
            or p.get("isForSale") is False
            or (
                p.get("availableInventory") is not None and p["availableInventory"] <= 0
            )
        )

    def clear(self) -> dict:
        r = self.s.delete(self._cart_url, headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.json()
