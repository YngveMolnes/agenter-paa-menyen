import unittest
from unittest.mock import Mock, patch

import requests

from matlevering import main
from matlevering.meny import Meny


class CartQuantityTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock(spec=requests.Session)
        self.session.headers = {"User-Agent": "fixture"}
        self.client = Meny(self.session, "fixture", store_gln="1234567890123")
        self.line = {"ean": "123", "quantity": 2, "pricePerUnit": 4, "__rev__": 7}
        self.cart = {"items": [self.line, {"ean": "456", "quantity": 1, "__rev__": 2}]}
        self.session.get.return_value.json.return_value = self.cart
        self.session.put.return_value.json.return_value = {"items": []}

    def test_cli_add_uses_one_snapshot_for_quantity_and_revision(self):
        with patch("matlevering._client", return_value=self.client), \
             patch("sys.argv", ["matlevering", "add", "123", "0.5"]), \
             patch("builtins.print"):
            main()
        self.session.get.assert_called_once()
        self.session.put.assert_called_once()
        items = self.session.put.call_args.kwargs["json"]["items"]
        self.assertEqual(items, [{**self.line, "quantity": 2.5, "__rev__": 8,
                                  "__removed__": False, "linePrice": 10}])

    def test_add_starts_from_zero_for_removed_item(self):
        self.line["__removed__"] = True
        result = self.client.add("123")
        item, = self.session.put.call_args.kwargs["json"]["items"]
        self.assertEqual(item["quantity"], 1)
        self.assertFalse(item["__removed__"])
        self.assertIn("addedTime", item)
        self.assertIs(result, self.session.put.return_value.json.return_value)

    def test_set_still_writes_absolute_quantities_in_one_batch(self):
        self.client.set_quantities({"123": 1, "456": 0})
        self.session.get.assert_called_once()
        self.session.put.assert_called_once()
        kept, removed = self.session.put.call_args.kwargs["json"]["items"]
        self.assertEqual(kept["quantity"], 1)
        self.assertTrue(removed["__removed__"])

    def test_add_does_not_repeat_a_timed_out_write(self):
        self.session.put.side_effect = requests.Timeout
        with self.assertRaises(requests.Timeout):
            self.client.add("123")
        self.session.put.assert_called_once()
