# meny.no webshop — API notes

Reverse-engineered from the meny.no/nettbutikk frontend bundles (Next.js, 2026-10-09).
The webshop is NorgesGruppen's shared "framework-core" platform; MENY is chain `1300`.

## Request conventions

- Base URL: `https://platform-rest-prod.ngdata.no`
- Path placeholder `{chainid}` → `1300`
- Headers sent by the frontend:
  - `Authorization: <userToken>` (only when logged in; the value already includes its scheme)
  - `Content-type: application/json`
  - `FWC-Chain-Id: 1300`
  - `FWC-Using-Bearer-Token: true|false`, `FWC-Using-Api-key: false`, `FWC-Browser-Platform: ...` (informational)

## Auth

- `GET https://meny.no/api/auth/getToken` returns the access token (a JWT, as a JSON string), based on the
  meny.no Auth.js session cookie. It returns `null` when there is no session. Header: `Authorization: Bearer <jwt>`.
  The JWT lives about 1 hour; getToken hands out fresh ones while the meny.no session lasts.
- Trumf ID login is phone number + password, then possibly an SMS code, a "register biometrics" offer and a
  "continue as" page. See `src/matlevering/auth.py` for the full flow.
- Login goes through Trumf ID: `/api/login?providerHandle=trumf-personal`.
- Login levels: `Unauthorized`, `Simplified`, `Bearer`. Some actions need `Bearer` (full password confirmation).

## Cart (requires login)

`/api/client-list-sync/1300/cart`

| Method | Purpose |
|--------|---------|
| GET    | Fetch the server-side cart |
| PUT    | Upload the whole cart (it replaces the cart, not a single line) |
| DELETE | Clear the cart |

Without the `Authorization` header it returns `401 {"message":"The request is missing the authorization header"}`.

Without a cart the GET returns `404 {"message":"Cart not found"}`.

PUT body (verified 2026-10-09):

```json
{"__id__": "cart", "__rev__": 1, "__removed__": false, "__type__": "CART", "__clientId__": "<guid>",
 "title": "cart", "__listRef__": "<guid>", "persistedId": "<guid>",
 "items": [{"id": "<ean>", "ean": "<ean>", "addedTime": "<iso>", "hasBeenSynced": false,
            "__rev__": 1, "__removed__": false, "__type__": "CART_PRODUCT", "quantity": 2,
            "pricePerUnit": 23.9, "linePrice": 47.8, "comparePricePerUnit": 23.9, "totalDiscount": 0,
            "linePriceAfterDiscount": null, "product": {<product hit, fieldset=maximal>},
            "doesNotExistInCurrentStore": false, "substitute": true, "shouldSlice": false}]}
```

Merge semantics (verified):
- Items in the body are upserted per EAN. Items left out are untouched, so sending `items: []` changes nothing.
- A quantity change is accepted with or without bumping the item `__rev__`; the client bumps it anyway.
- Removal: send the item with `__removed__: true`. The server keeps it as a tombstone in `items`.
- `DELETE` empties `items` and bumps the cart `__rev__`.

### Price calculator

`PUT /api/calculator/1300` (anonymous users add `/<storeGln>`)
- Query: `bagtype`, `editmode`, `handoverType`, optional `servicefeetype` and `handoverdate`
- Body: an array of `{ean, quantity, pricePerUnit, linePrice, comparePricePerUnit, totalDiscount, linePriceAfterDiscount, product: null}`

## Products (no login needed)

`GET /api/products/1300/{storeGln}?search=<q>&page=1&page_size=N&fieldset=minimal|maximal`

`storeGln=0` works for anonymous search, but returns 0 hits when the user token is sent and the user has
no store chosen, so search runs without the token. `product_ids=<ean>,<ean>` fetches specific products. Hits include `ean`, `title`, `subtitle`, `pricePerUnit`, `unitRule`, `isForSale`.

Alternative: `https://productsearchapi.trumfnetthandel.prod.trumf.cloud/products/v1/1300/{gln}/search/minimal`.
It returns 0 hits with `gln=0`, so it probably needs a real store GLN.

## Other endpoints seen

handover windows (`/api/handoverwindows/delivery/1300/{gln}`), `/api/handoveroptions/1300`,
`/api/extended-user/1300/household`, `/api/stored-shopping-lists/...`, `/api/order/1300/...`,
`/api/coupon/1300`, `/api/stores/1300/{gln}/status`, `/api/delivery/coverage/1300/{postcode}`.

## API documentation (Swagger/OpenAPI) search

- `platform-rest-prod.ngdata.no` — Node service (`GET /` → `{"data":"running","appVersion":"9.36.0"}`).
  No docs at any common swagger/openapi/fastify/express path.
- `productsearchapi.trumfnetthandel.prod.trumf.cloud` — Azure Function App with the OpenAPI extension.
  `/swagger/ui`, `/openapi/v3.json`, `/openapi/v2.json` exist but return 401 ("Authorization header is missing").
  Worth retrying with a logged-in user token.
- `api.ngdata.no` / `api.sylinder.no` — Azure API Management gateways ("Resource not found" at root).
  Developer portal: `https://developer.ngdata.no` (NorgesGruppen Data AS). Anonymous
  `GET /developer/apis?api-version=2022-04-01-preview` returns an empty list; sign-up is open (`/signup`).

### developer.ngdata.no catalogue (logged in, 2026-10-09)

78 APIs, all served by the APIM gateway `https://api.ngdata.no/<path>`; the `sylinder/*` ones are
also reachable as `https://api.sylinder.no/<path without "sylinder/">` (the frontend does exactly that).
The exported OpenAPI documents have no paths for this account, but the operation lists are readable.

**None of them is a general cart/basket API.** The webshop cart lives only in the
`platform-rest-prod.ngdata.no` service, which isn't in APIM.

Most relevant to us:

| APIM path | Operations |
|-----------|------------|
| `sylinder/handlevogn/delehandlevogn` | `POST /api`, `GET /api/{id}` — shared cart ("delt handlevogn") snapshots |
| `sylinder/search/productsearch` | `GET /search/{gln}/products`, `GET /search/varer`, `GET /lookup/products`, `GET /categories`, `GET /search/{gln}/products/{gtin}/similar` |
| `sylinder/deliverycalendar` | `POST /handoverwindows/{type}/{chain}/{gln}` — **no subscription key required** |
| `sylinder/hentevinduer/reservasjoner` | `POST /api`, `PUT /api/{id}/confirm`, `PUT /api/{id}/extend`, `DELETE /api/{id}` — time-slot reservations |
| `sylinder/hentevinduer/utleveringskalender` | `GET /kjeder/{kjedeId}/soner`, `GET /kjeder/{kjedeId}/dekning` |
| `sylinder/netthandel/leveringsadresser` | `GET /adresser/sok`, ... |
| `sylinder/stores`, `stores` | store lookup (basic/extended info, nearest, search, findstore/*) |
| `sylinder/varer/varepriser`, `sylinder/varer/beholdning` | prices / stock per store GLN |
| `sylinder/passwordless` | `GET /authorize`, `POST /token`, ... |

Access: every API except `sylinder/deliverycalendar` and `sylinder/singlesignon` needs a subscription key.
Products open without approval: `Starter`, `ServiceHub`. All others need approval. The account currently has no subscriptions.
