import io
import unittest
from unittest.mock import patch

import requests

from examples import search_recipes


def card(title, slug, parent=None):
    return {"document": {"type": "recipe", "title": title, "slug": slug, "parentSlug": parent}}


class RecipeSearchTests(unittest.TestCase):
    def setUp(self):
        self.get = self.enterContext(patch.object(search_recipes.requests, "get"))
        self.response = self.get.return_value
        self.enterContext(patch("sys.argv", ["search_recipes.py", "fisk", "og", "ris"]))
        self.output = self.enterContext(patch("sys.stdout", new_callable=io.StringIO))

    def test_command_prints_ranked_titles_and_links(self):
        self.response.json.return_value = {"recipes": {"hits": [
            card("Ørret med ris", "orret-med-ris", "fisk"),
            card("Fiskesuppe", "fiskesuppe"),
        ]}}
        search_recipes.main()
        self.assertEqual(self.output.getvalue().splitlines(), [
            "Ørret med ris  https://meny.no/oppskrifter/fisk/orret-med-ris",
            "Fiskesuppe  https://meny.no/oppskrifter/fiskesuppe",
        ])
        self.get.assert_called_once()
        self.assertEqual(self.get.call_args.kwargs["params"],
                         {"query": "fisk og ris", "include": "recipes", "page": 1, "size": 10})

    def test_empty_page(self):
        self.response.json.return_value = {"recipes": {"hits": []}}
        search_recipes.main()
        self.assertEqual(self.output.getvalue(), "No recipes found.\n")

    def test_unexpected_payload_or_link_fails_before_printing(self):
        for payload in ({}, {"recipes": {"hits": [card("Fish", "../cart")]}}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.response.json.return_value = payload
                search_recipes.search_recipes("fisk")

    def test_http_failure_exits_without_results(self):
        self.response.raise_for_status.side_effect = requests.HTTPError("unavailable")
        with patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit) as raised:
            search_recipes.main()
        self.assertEqual(raised.exception.code, 1)
        self.response.json.assert_not_called()
        self.assertEqual(self.output.getvalue(), "")
