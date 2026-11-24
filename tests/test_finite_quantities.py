import math
import unittest
from unittest.mock import Mock, patch

import requests

from matlevering import main
from matlevering.meny import Meny


class FiniteQuantityTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock(spec=requests.Session)
        self.session.headers = {"User-Agent": "fixture"}
        self.client = Meny(self.session, "fixture", store_gln="1234567890123")
        self.line = {"ean": "123", "quantity": 2, "pricePerUnit": 4, "__rev__": 1}
        self.session.get.return_value.json.return_value = {"items": [self.line]}
        self.session.put.return_value.json.return_value = {"items": []}

    def test_cli_rejects_nan_instead_of_removing_item(self):
        for command in ("add", "set"):
            with (
                self.subTest(command=command),
                patch("sys.argv", ["matlevering", command, "123", "nan"]),
                patch("matlevering._client", return_value=self.client),
            ):
                with self.assertRaisesRegex(SystemExit, "must be finite"):
                    main()
                self.session.put.assert_not_called()

    def test_invalid_quantity_rejects_whole_batch_before_product_lookup(self):
        for quantity in (math.nan, math.inf, -math.inf):
            with (
                self.subTest(quantity=quantity),
                patch.object(self.client, "products") as lookup,
            ):
                with self.assertRaisesRegex(ValueError, "must be finite"):
                    self.client.set_quantities({"456": 1, "123": quantity})
                lookup.assert_not_called()
                self.session.put.assert_not_called()

    def test_relative_add_rejects_overflowed_target(self):
        self.line["quantity"] = 1e308
        with self.assertRaisesRegex(ValueError, "must be finite"):
            self.client.add("123", 1e308)
        self.session.put.assert_not_called()

    def test_fractional_add_and_zero_removal(self):
        self.client.add("123", 0.5)
        item, = self.session.put.call_args.kwargs["json"]["items"]
        self.assertEqual(item["quantity"], 2.5)
        self.assertFalse(item["__removed__"])

        self.client.set_quantities({"123": 0})
        item, = self.session.put.call_args.kwargs["json"]["items"]
        self.assertTrue(item["__removed__"])
