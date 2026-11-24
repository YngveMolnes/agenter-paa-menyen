# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Per Oskar Isdahl
"""Find published MENY recipes by title and link. No store or login required."""

import argparse
import re

import requests

from matlevering.auth import USER_AGENT

# Public recipe search documented in poisdahl/meal-concierge#435.
SEARCH_URL = "https://search.trumfnetthandel.prod.trumf.cloud/search/all/1300"
PAGE_SIZE = 10


def search_recipes(query: str) -> list[tuple[str, str]]:
    response = requests.get(
        SEARCH_URL,
        params={"query": query, "include": "recipes", "page": 1, "size": PAGE_SIZE},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    group = payload.get("recipes") if isinstance(payload, dict) else None
    hits = group.get("hits") if isinstance(group, dict) else None
    total = group.get("totalCount") if isinstance(group, dict) else None
    if (type(total) is not int or total < 0 or not isinstance(hits, list)
            or len(hits) != min(total, PAGE_SIZE)):
        raise ValueError("MENY returned an unexpected recipe search response")

    recipes = []
    for hit in hits:
        card = hit.get("document") if isinstance(hit, dict) else None
        if not isinstance(card, dict) or card.get("type") != "recipe":
            raise ValueError("MENY returned an unexpected recipe card")
        title, slug, parent = card.get("title"), card.get("slug"), card.get("parentSlug")
        parts = [slug] if parent in ("", None) else [parent, slug]
        if not isinstance(title, str) or not title.strip() or not all(
            isinstance(part, str) and re.fullmatch(r"[a-zA-Z0-9_-]+", part) for part in parts
        ):
            raise ValueError("MENY returned an unexpected recipe title or link")
        recipes.append((" ".join(title.split()), "https://meny.no/oppskrifter/" + "/".join(parts)))
    return recipes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="+")
    try:
        recipes = search_recipes(" ".join(parser.parse_args().query))
    except (requests.RequestException, ValueError) as exc:
        parser.exit(1, f"Recipe search failed: {exc}\n")
    if not recipes:
        print("No recipes found.")
    for title, url in recipes:
        print(f"{title}  {url}")


if __name__ == "__main__":
    main()
