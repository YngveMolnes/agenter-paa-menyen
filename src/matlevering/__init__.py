import argparse
import base64
import json
import sys
from datetime import datetime

from .auth import LoginError, get_session, login
from .meny import Meny


def _jwt_claims(token: str) -> dict:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def _client() -> Meny:
    return Meny(*get_session())


def _print_cart(cart: dict) -> None:
    items = [i for i in cart["items"] if not i.get("__removed__")]
    if not items:
        print("Cart is empty.")
        return
    total = 0.0
    for i in items:
        p = i.get("product") or {}
        line = i["pricePerUnit"] * i["quantity"]
        total += line
        flag = "  [UNAVAILABLE]" if Meny.unavailable(i) else ""
        print(
            f"{i['ean']}  {i['quantity']:>4g} x {p.get('title', '?')} {p.get('subtitle', '')}  {line:.2f} kr{flag}"
        )
    print(f"Total (list prices, before discounts): {total:.2f} kr")


def cmd_login(args) -> None:
    _, token = login(otp=args.otp)
    claims = _jwt_claims(token)
    exp = (
        datetime.fromtimestamp(claims["exp"]).astimezone().isoformat(timespec="minutes")
        if "exp" in claims
        else "?"
    )
    print(f"Logged in. Token expires {exp}.")


def cmd_token(args) -> None:
    _, token = get_session()
    print(token)


def cmd_search(args) -> None:
    for p in _client().search(" ".join(args.query), page_size=args.limit):
        print(
            f"{p['ean']}  {p['title']} {p.get('subtitle', '')}  {p['pricePerUnit']:.2f} kr"
        )


def cmd_store(args) -> None:
    session, token = get_session()
    store = Meny(session, token, store_gln="0").user_store()
    if not store:
        sys.exit("No store is set on your profile. Choose one on meny.no first.")
    print(
        f"{store.get('name')}, {store.get('address', '')} {store.get('postalCode', '')} {store.get('city', '')}".strip()
    )
    print(f"GLN {store['gln']}")


def cmd_cart(args) -> None:
    cart = _client().get_cart()
    if args.json:
        print(json.dumps(cart, indent=2, ensure_ascii=False))
    else:
        _print_cart(cart)


def cmd_add(args) -> None:
    _print_cart(_client().add(args.ean, args.quantity))


def cmd_set(args) -> None:
    _print_cart(_client().set_quantities({args.ean: args.quantity}))


def cmd_remove(args) -> None:
    _print_cart(_client().remove(args.ean))


def cmd_refresh(args) -> None:
    _print_cart(_client().refresh())


def cmd_clear(args) -> None:
    _print_cart(_client().clear())


def main() -> None:
    parser = argparse.ArgumentParser(prog="matlevering")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "login", help="log in with TRUMF_USERNAME/TRUMF_PASSWORD and save the session"
    )
    p.add_argument(
        "--otp", help="SMS code, to finish a login that stopped at the SMS step"
    )
    p.set_defaults(func=cmd_login)

    sub.add_parser(
        "token", help="print a fresh access token from the saved session"
    ).set_defaults(func=cmd_token)

    p = sub.add_parser("search", help="search for products")
    p.add_argument("query", nargs="+")
    p.add_argument("-n", "--limit", type=int, default=10)
    p.set_defaults(func=cmd_search)

    sub.add_parser(
        "store", help="show the store chosen on your Trumf/MENY profile"
    ).set_defaults(func=cmd_store)

    p = sub.add_parser("cart", help="show the cart")
    p.add_argument("--json", action="store_true", help="print the raw cart JSON")
    p.set_defaults(func=cmd_cart)

    p = sub.add_parser("add", help="add a product (by EAN) to the cart")
    p.add_argument("ean")
    p.add_argument("quantity", nargs="?", type=float, default=1)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("set", help="set the quantity of a product (0 removes it)")
    p.add_argument("ean")
    p.add_argument("quantity", type=float)
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("remove", help="remove a product from the cart")
    p.add_argument("ean")
    p.set_defaults(func=cmd_remove)

    sub.add_parser(
        "refresh",
        help="re-sync products and prices with your store, flag unavailable items",
    ).set_defaults(func=cmd_refresh)

    sub.add_parser("clear", help="empty the cart").set_defaults(func=cmd_clear)

    args = parser.parse_args()
    try:
        args.func(args)
    except (LoginError, ValueError) as e:
        sys.exit(f"error: {e}")
