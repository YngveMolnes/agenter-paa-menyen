import io
import json
import runpy
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

import requests


SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "add_from_list.py"


class ShoppingListTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock(spec=requests.Session)
        self.session.headers = {"User-Agent": "fixture"}
        self.catalog = Mock(spec=requests.Session)
        self.catalog.headers = {}
        self.store = {"gln": "1234567890123", "name": "Fixture store"}
        self.cart = {"items": []}
        self.products = []
        self.session.get.side_effect = self.get
        self.catalog.get.side_effect = self.get_products

    def get(self, url, **kwargs):
        if "/api/extended-user/" in url:
            payload = {"store": self.store}
        else:
            self.assertTrue(url.endswith("/cart"), url)
            payload = self.cart
        return Mock(status_code=200, **{"json.return_value": payload})

    def get_products(self, url, *, params, **kwargs):
        self.assertTrue(url.endswith("/" + self.store["gln"]), url)
        ids = params["product_ids"].split(",")
        hits = [p for p in self.products if p["ean"] in ids]
        return Mock(**{"json.return_value": {"hits": hits}})

    def run_list(self, quantities, apply=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "list.json"
            path.write_text(json.dumps([{"ean": k, "quantity": v} for k, v in quantities.items()]))
            argv = [str(SCRIPT), str(path)] + (["--apply"] if apply else [])
            output = io.StringIO()
            with (
                patch.object(sys, "argv", argv),
                patch("matlevering.auth.get_session", return_value=(self.session, "fixture")),
                patch("matlevering.meny.requests.Session", return_value=self.catalog),
                redirect_stdout(output),
            ):
                runpy.run_path(str(SCRIPT), run_name="__main__")
            return output.getvalue()

    def test_store_scoped_preview_and_absolute_batch(self):
        def product(ean, **kwargs):
            return {"ean": ean, "title": ean, "pricePerUnit": 5, "comparePricePerUnit": 5, **kwargs}

        self.products = [product("in"), product("zero", availableInventory=0)]
        self.cart["items"] = [
            {"ean": "in", "quantity": 1, "pricePerUnit": 5},
            {"ean": "delisted", "quantity": 2, "pricePerUnit": 1},
        ]
        targets = {"in": 1.5, "zero": 1, "delisted": 0, "absent": 0}
        preview = self.run_list(targets)
        self.assertIn("Store: Fixture store", preview)
        self.assertIn("not available at your store: zero", preview)
        self.assertIn("2 -> 0  delisted", preview)
        self.assertIn("Dry run", preview)
        self.session.put.assert_not_called()
        self.assertEqual(self.catalog.get.call_args.kwargs["params"]["product_ids"], "in,zero")
        self.assertEqual(self.session.get.call_count, 2)  # profile and cart

        self.run_list(targets, apply=True)
        self.session.put.assert_called_once()
        changed = self.session.put.call_args.kwargs["json"]["items"]
        self.assertEqual([i["ean"] for i in changed], ["in", "delisted"])
        self.assertEqual(changed[0]["quantity"], 1.5)
        self.assertTrue(changed[1]["__removed__"])

    def test_missing_store_stops_positive_batch(self):
        self.store = {}
        with self.assertRaisesRegex(SystemExit, "Choose a store"):
            self.run_list({"new": 1, "old": 0}, apply=True)
        self.catalog.get.assert_not_called()
        self.session.put.assert_not_called()

    def test_removal_only_needs_no_catalog_or_store(self):
        self.store = {}
        self.cart["items"] = [{"ean": "old", "quantity": 2}]
        self.run_list({"old": 0, "absent": 0}, apply=True)
        self.catalog.get.assert_not_called()
        self.session.put.assert_called_once()
        changed, = self.session.put.call_args.kwargs["json"]["items"]
        self.assertEqual(changed["ean"], "old")
        self.assertTrue(changed["__removed__"])

    def test_invalid_quantity_stops_before_any_change(self):
        for quantity in (float("nan"), -1, True, "2"):
            with self.subTest(quantity=quantity), self.assertRaisesRegex(SystemExit, "quantity"):
                self.run_list({"old": quantity}, apply=True)
        self.session.get.assert_not_called()
        self.session.put.assert_not_called()
