# API reference

## Conventions

Navigate to [Users](#users), [Products](#products), [Cart](#cart),
[Orders](#orders), or [Payments](#payments). Identity/session workflows belong in
[Authentication](authentication.md); controls and limitations are in
[Security](security.md).

Application API routes are under `/api/v1/`. Normal bodies are JSON. Send an
access token for protected endpoints:

```http
Authorization: Bearer <access-token>
```

User routes begin `/api/v1/users/`; product routes begin `/api/v1/products/`;
Cart routes begin `/api/v1/cart/`; Order routes begin `/api/v1/orders/`; and
Payment routes begin `/api/v1/payments/`. Examples with placeholder tokens,
UUIDs, or product values are illustrative unless their fields are explicitly
listed below.

Human-readable messages negotiate Django language in the usual order: a valid
language cookie, then `Accept-Language` (including compatible variants such as
`fa-IR`), then English. Supported languages are `en` and `fa`; unsupported or
missing preferences fall back to English. JSON field names, validation keys,
status values, response `code` values, URLs, query parameters, and headers are
stable machine contracts and are never translated.

### Requests, identifiers, and errors

Send `Content-Type: application/json` for JSON bodies and `Accept: application/json`
for JSON representations. Image upload uses multipart instead. A 204 has no
body; clients must not parse it as JSON. DRF errors generally use `detail` for
authentication/permission/not-found/throttle failures and field keys or
`non_field_errors` for validation. Values can be strings, lists, or nested
objects; there is no universal `data` or `error` wrapper. For example:

```json
{"quantity": ["Requested quantity exceeds available stock."]}
```

Only explicitly returned `code` fields are stable JSON error codes; an internal
DRF exception code is not automatically a response field. Unsupported methods
return 405; invalid pagination pages can return 404. Throttle responses may
include `Retry-After`, separately from Payment pending guidance.

Paths below include `/api/v1/` and trailing slashes. Angle brackets denote path
parameters, not literal characters. Product/Cart item lookups use exact slugs;
image deletion uses an integer ID; Order/Payment detail uses UUIDs. User/Cart
identity comes from authentication. Identifiers never grant authorization.
Profile/address `id` values and catalogue relation references are UUIDs. Product
response UUIDs differ from internal integer IDs. Dates/times are ISO 8601 strings.

Cross-origin browser clients must include credentials for refresh-cookie
operations and satisfy the Users Origin policy. JavaScript receives no refresh
token. See [JWT lifecycle](authentication.md#jwt-lifecycle-and-cookie-contract).

## Users

### Endpoint contracts

In this table, **Origin** means `CookieAuthOriginPermission`: an exact `Origin`
matching the API scheme/host or `CORS_ALLOWED_ORIGINS` is required, including for
non-browser clients. Missing/untrusted Origin returns 403. **Authenticated**
means bearer JWT authentication for the current active user. Global permissions
are `IsAuthenticated`; public access is an explicit view override. Refresh and
logout disable bearer authentication. Other public Users views generally retain
the default JWT authenticator, so an invalid Authorization header can cause 401.
Capabilities also disables authentication and needs no cookie or Origin.

| Method and path | Access | Request | Success |
| --- | --- | --- | --- |
| `POST /api/v1/users/signup/` | Anonymous-capable; signup throttle; Origin | `username`, `password` | 201; `user.username`, `tokens.access`, and refresh cookie |
| `POST /api/v1/users/signup/send-otp/` | Public; phone + IP OTP-request throttles | `phone_number` | 200; message and `expires_in` |
| `POST /api/v1/users/signup/verify-otp/` | Anonymous-capable; phone + IP verification throttles; Origin | `phone_number`, `otp` | 201; message, `tokens.access`, and refresh cookie |
| `POST /api/v1/users/login/userpass/` | Anonymous-capable; password-login throttle; Origin | `username`, `password` | 200; message, `tokens.access`, and refresh cookie |
| `POST /api/v1/users/token/refresh/` | Cookie operation; refresh throttle; Origin | Refresh cookie | 200; rotated `access` and refresh cookie |
| `POST /api/v1/users/login/send-otp/` | Public; phone + IP OTP-request throttles | `phone_number` | 200; message and `expires_in` |
| `POST /api/v1/users/login/verify-otp/` | Anonymous-capable; phone + IP verification throttles; Origin | `phone_number`, `otp` | 200; message, `tokens.access`, and refresh cookie |
| `POST /api/v1/users/profile/phone/send-otp/` | Authenticated; phone + IP OTP-request throttles | `phone_number` | 200; generic message and `expires_in` |
| `POST /api/v1/users/profile/phone/verify-otp/` | Authenticated; phone + IP OTP-verification throttles | `phone_number`, `otp` | 200; verified serialized user in `data` |
| `GET /api/v1/users/profile/` | Authenticated | No body or user identifier | 200; current serialized user in `data` |
| `POST /api/v1/users/profile/complete/` | Authenticated; requires an existing phone established by a supported verification flow | `username`, `email`, `first_name`, `last_name`, `address` | 200; message and serialized user in `data` |
| `PATCH /api/v1/users/profile/update/` | Authenticated | Any subset of `username`, `email`, `first_name`, `last_name`, `address` | 200; message and serialized user in `data` |
| `GET /api/v1/users/auth-capabilities/` | Public | No body | 200; `sms_available` boolean |
| `POST /api/v1/users/password/change/` | Authenticated; IP throttle | `current_password`, `password` | 200; message and expired refresh cookie; sign in again |
| `POST /api/v1/users/password/set/send-otp/` | Authenticated OTP-only account; account + IP throttle | No input fields (send `{}`) | 200; message and `expires_in`; session unchanged |
| `POST /api/v1/users/password/set/verify/` | Authenticated OTP-only account; account + IP throttle | `otp`, `password` | 200; message and expired refresh cookie; sign in again |
| `POST /api/v1/users/logout/` | Cookie operation; Origin | No body | 200; logout message and expired cookie |
| `POST /api/v1/users/password-reset/send-otp/` | Public; phone + IP OTP-request throttles | `phone_number` | 200; message and `expires_in` |
| `POST /api/v1/users/password-reset/verify-and-reset/` | Anonymous-capable; phone + IP verification throttles; Origin | `phone_number`, `otp`, `password` | 200; message, `tokens.access`, and refresh cookie |

### Validation, errors, and session effects

Signup creates an active username-only account with an incomplete profile.
Case-insensitive/concurrent username conflicts return generic 400
`non_field_errors`. Password login returns the same 401 `detail` for unknown,
inactive, OTP-only, and incorrect-password accounts.

SMS-dependent OTP services return generic 503 while delivery is disabled or
misconfigured. Password-based authentication and password change remain available.
Profile writes reject password fields; recovery requires an existing usable password.

`phone_number` must match ASCII `09[0-9]{9}`, such as `09123456789`; Unicode
digits and alternate formats are rejected. OTPs are exactly six ASCII digits.
Refresh responses rotate the cookie refresh token and blacklist its prior
value. Password changes invalidate older access and refresh tokens. Sensitive
auth views apply no-store headers. Detailed session behavior is in
[Authentication](authentication.md).

Usernames supplied by signup, profile completion, or profile update must be
5–150 ASCII letters, digits, or underscores after trimming. Password fields
preserve whitespace and have a 128-character API maximum. New passwords satisfy
all configured Django validators, including a 12-character minimum; see
[password policy](authentication.md#identity-and-password-rules).

Initial setup requires an active account without a usable password, an account
phone, a nonblank normalized username, and operational SMS. Save a username
through profile update first if missing. Requesting the code changes no
credential, token, or cookie. Only successful verification saves the password,
revokes prior sessions, and expires the refresh cookie; no replacement JWT is
issued. Change Password has the same successful session effects and requires
the correct current password; wrong current credentials/ineligibility return 400.
Recovery requires an active password account and returns a replacement session.

OTP-request responses contain `message` and `expires_in` (default 120 seconds), never
a code or delivery receipt. With operational SMS, signup requests for existing
phones, login requests for unknown phones, reset requests for unknown/inactive/
OTP-only accounts, and profile-phone requests for ineligible/already-owned phones
retain generic success responses. Verification still checks eligibility.
Invalid, expired, mismatched, or redeemed codes return 400 under `otp`. Lockouts,
overlapping verification, and throttles can return 429; protection-cache failure
returns 503. These checks can precede business validation.

Direct signup has this shape (illustrative values):

```json
{"user": {"username": "sample_customer"}, "tokens": {"access": "<access-token>"}}
```

Password login, OTP login/signup verification, and recovery return
`{"message": "<message>", "tokens": {"access": "<access-token>"}}` and set the
refresh cookie. Refresh alone returns top-level `access`. Change/setup success
and logout return only `message`; capabilities returns only `sms_available`.
Profile-phone verification and profile writes return `message` and `data`;
profile GET returns only `data`.

### Profile and address representation

`GET /api/v1/users/profile/` always resolves the authenticated user and does not accept
a user ID. It returns `{"data": <serialized-user>}` and prefetches that user's
addresses in creation order.

Profile completion requires all listed personal fields and creates the first
address; a missing phone or an existing address returns 400. Partial update
accepts any subset of supported fields. Email must be valid and unique ignoring
case. Names are capped at 50 characters; PATCH permits blank names (which can
make the profile incomplete). Neither endpoint accepts credential mutation.

The nested `address` has required `title` (at most 50 characters) and
`full_address`, plus optional blank/nullable `postal_code` (at most 10 characters;
not a digits-only validator). To edit an existing address, PATCH must include
that owned address's UUID `id` plus at least one changed field. A foreign/missing
address ID returns 400. Without an ID, PATCH only creates an address for a user
with none and requires title/full address. Omission leaves addresses unchanged.

The serialized user has `id`, `phone_number`, `username`, `email`, `first_name`,
`last_name`, `is_profile_complete`, `addresses`, `has_usable_password`, and
`sms_available`. An address has `id`, `title`, `full_address`, and `postal_code`.
GET returns addresses in creation order; absent username/email/phone can be null.
This representation excludes passwords, tokens, staff/group/permission fields.
Ordinary profile writes and phone verification issue no JWT and preserve sessions.

## Products

### Routes and write contract

| Method and path | Access | Request / behavior | Success |
| --- | --- | --- | --- |
| `GET /api/v1/products/` | Public; catalogue-read throttle | Lists active products | 200; paginated product list |
| `POST /api/v1/products/` | Authenticated staff only; existing user throttle | Product write fields | 201; product detail |
| `GET /api/v1/products/<product_slug>/` | Public; catalogue-read throttle | Retrieves an active product; staff can retrieve inactive products | 200; product detail |
| `PUT /api/v1/products/<product_slug>/` | Authenticated staff only; existing user throttle | Complete product write fields | 200; product detail |
| `PATCH /api/v1/products/<product_slug>/` | Authenticated staff only; existing user throttle | Partial product write fields | 200; product detail |
| `DELETE /api/v1/products/<product_slug>/` | Authenticated staff only; existing user throttle | — | 204; no body |
| `POST /api/v1/products/<product_slug>/images/upload/` | Authenticated staff only | Multipart form data | 201; image object |
| `DELETE /api/v1/products/images/<image_id>/` | Authenticated staff only | `image_id` is an integer | 204; no body |

`product_slug` is the product's exact, case-sensitive public slug. Product
slugs must be lowercase, cannot use canonical UUID syntax, and cannot change
after creation. UUID product URLs are not supported. Product write fields are
`category`, optional nullable `brand`, `name`, `slug`, `sku`, `description`,
`price`, optional `discount_price`, `stock`, `volume_ml`, optional `country_of_origin`,
`concentration`, `target_audience`, `fragrance_family`, optional nullable
`introduction_year`, `suitable_season`, `suitable_usage_time`, optional
nullable `barcode`, optional UUID arrays `top_notes`, `middle_notes`, and
`base_notes`, `is_active`, and `is_featured`. `category`, `brand`, and note
values use UUID primary keys; the category must be active and every referenced
note must already exist. Each note array is ordered: the first UUID receives
position 1, and create/update responses return the exact submitted order. A
note cannot be repeated within one layer, but the same note may appear in
different layers. An omitted note layer is preserved on PATCH, while an
explicit empty array clears it. Product types such as perfume, cologne, and
Body Splash are represented by `Category`; they are not concentration values.

POST and non-partial PUT require `category`, `name`, `slug`, `sku`, `description`,
`price`, and `volume_ml`. Other fields are optional; model defaults include stock
0, active true, featured false, and unspecified classifications. Omitted optional
fields, including note layers, are preserved on PUT/PATCH; creation uses model
defaults where available. PATCH validates supplied changes against existing
Product values.
No public Category, Brand, or FragranceNote management endpoints are registered.

`price` and non-null `discount_price` must be at least `0.01`, with at most 12
digits including two decimal places. Stock is a non-negative integer.
`volume_ml` must be positive. `discount_price`, when provided, must be lower
than `price`. `introduction_year` must be between 1700 and the current year.
`barcode` is distinct from `sku`; when present it must be unique and contain
8–14 ASCII digits. An empty barcode is stored as null so multiple products can
omit it. Fragrance classifications default to the explicit neutral value
`unspecified`; this is a model default, not evidence of a legacy data migration.

### Read representations

Product-list output fields are `uuid`, `name`, `slug`, `sku`, `price`,
`discount_price`, `final_price`, `stock`, `concentration`, `target_audience`,
`fragrance_family`, `introduction_year`, `suitable_season`,
`suitable_usage_time`, `volume_ml`, `category`, `brand`, `primary_image`,
`is_featured`, and `created_at`. Detail omits list-only `primary_image` and adds
`description`,
`country_of_origin`, `barcode`, `top_notes`, `middle_notes`, `base_notes`,
`is_active`, `images`, and `updated_at`. Each note summary has `uuid`, `name`,
and `slug`, and each layer array is in its persisted position order. Category
summaries have `uuid`, `name`, and `slug`; brand
summaries add `country`. An image object has integer `id`, `image`, `thumbnail`,
`is_primary`, and `display_order`.

The product `uuid` remains a stable response identifier but is not a URL lookup
value.

`brand` and `primary_image` can be null. Detail uses `images` (empty when absent);
a missing thumbnail is null. Media URLs are storage/request-derived. Prices,
including non-null discounts and `final_price`, are two-decimal strings.
`final_price` uses the discount when set; filtering/ordering by `price` uses the
regular price, not this computed value.

A Product referenced by immutable OrderItem history cannot be deleted because
the database relationship uses `PROTECT`; that DELETE returns `409`. Staff can
set `is_active=false` when a commercially referenced Product must leave the
catalogue.

### Fragrance choices

- `concentration`: `unspecified`, `extrait_de_parfum`, `parfum`,
  `eau_de_parfum`, `eau_de_toilette`, or `eau_de_cologne`.
- `target_audience`: `unspecified`, `women`, `men`, `unisex`, or `kids`.
- `fragrance_family`: `unspecified`, `amber`, `aromatic`, `aquatic`, `chypre`,
  `citrus`, `floral`, `fougere`, `fruity`, `gourmand`, `green`, `leather`,
  `musk`, `powdery`, `spicy`, `woody`, or `other`.
- `suitable_season`: `unspecified`, `spring`, `summer`, `autumn`, `winter`, or
  `all_seasons`.
- `suitable_usage_time`: `unspecified`, `day`, `night`, or `day_and_night`.

### Product list query parameters

`GET /api/v1/products/` accepts:

- Pagination: `page` and `page_size` (default 12, maximum 100).
- Search: `search` across name, SKU, description, brand name, category name,
  and top, middle, or base note names.
- Ordering: `ordering` with `price`, `created_at`, `introduction_year`, `stock`,
  `name`, or `volume_ml`; prefix a field with `-` for descending order.
  Default: `-created_at`.
- Filters: category slug `category` (for example, `?category=men`; includes
  products in that category and every descendant category), UUID `brand`,
  boolean `is_featured`, exact case-insensitive `country_of_origin`, exact
  `concentration`,
  `target_audience`, `fragrance_family`, `introduction_year`,
  `suitable_season`, `suitable_usage_time`, UUID `note` across all three note
  layers, `min_price` and `max_price` against the regular `price` field, and
  boolean `in_stock` (`true` selects
  stock above zero; `false` selects zero stock).

Products and Orders use this page-number envelope (an empty-page example).
For populated pages, `results` contains the endpoint's list objects and `links`
contains next/previous URLs or null:

```json
{
  "count": 0,
  "total_pages": 1,
  "current_page": 1,
  "page_size": 12,
  "links": {"next": null, "previous": null},
  "results": []
}
```

Anonymous and authenticated non-staff product-list and detail requests share
the same default Redis cache when available; the response contains no
user-specific catalogue data, so cache keys never include a user identifier.
Staff requests bypass that shared cache because staff may retrieve inactive
product details. `Product.is_active` controls catalogue visibility for public
and non-staff requests; it is unrelated to `User.is_active`, which controls
account state. Cache behavior does not change visibility rules.

### Image upload

`POST /api/v1/products/<product_slug>/images/upload/` requires `multipart/form-data` with:

- `image` — required JPEG, PNG, or WebP upload.
- `is_primary` — optional boolean, default `false`.
- `display_order` — optional non-negative integer, default `0`.

The server checks declared MIME type, decoded format, MIME/content consistency,
corruption, decompression-bomb warnings, a 5 MiB (5 × 1024 × 1024 bytes) size
limit, and a 6000 × 6000 dimension limit. It generates a safe filename. The
returned integer image ID is the lookup value for image deletion. Thumbnail
processing is asynchronous; a successful upload need not yet have a thumbnail.

## Cart

Every Cart endpoint requires authentication but does not require a complete
profile. Cart ownership always comes from the access token; requests and URLs
never accept a user ID. There are no anonymous or session carts and no
pagination.

| Method and path | Request / behavior | Success |
| --- | --- | --- |
| `GET /api/v1/cart/` | Read the current user's Cart; never creates one | 200; full Cart |
| `DELETE /api/v1/cart/` | Clear all items; retain an existing empty Cart | 204; no body |
| `POST /api/v1/cart/items/` | `product_slug`, `quantity`; add quantity to an existing item | 201 for a new item or 200 for an increment; full Cart |
| `PATCH /api/v1/cart/items/<product_slug>/` | `quantity`; set the absolute owned-item quantity | 200; full Cart |
| `DELETE /api/v1/cart/items/<product_slug>/` | Remove the owned item | 204; no body |

`quantity` must be at least 1. A POST product must currently be active, and
the resulting quantity may not exceed current stock. Missing and inactive POST
products both return 404. PATCH uses current stock and returns 404 when the
user does not own an item with that exact, case-sensitive Product slug.
Existing inactive items remain visible and may be patched when current stock
covers the requested quantity; they remain unavailable. Deleting or clearing
a missing Cart is respectively 404 for an item and idempotent 204 for the
whole Cart.

Quantity validation/current-stock excess returns 400 under `quantity`. A missing
Cart reads as `{"items": [], "total_quantity": 0, "total_price": "0.00",
"has_unavailable_items": false}` without creating a row.

A full Cart has this shape:

```json
{
  "items": [
    {
      "product": {
        "uuid": "550e8400-e29b-41d4-a716-446655440000",
        "slug": "example-perfume",
        "name": "Example Perfume",
        "primary_image": {
          "id": 1,
          "image": "https://example.test/media/products/example.jpg",
          "thumbnail": "https://example.test/media/products/thumbnails/example.webp",
          "is_primary": true,
          "display_order": 0
        }
      },
      "quantity": 2,
      "unit_price": "80.00",
      "line_total": "160.00",
      "available_stock": 5,
      "available": true
    }
  ],
  "total_quantity": 2,
  "total_price": "160.00",
  "has_unavailable_items": false
}
```

`primary_image` is null when the Product has no images. Prices and line/cart
totals use decimal strings. `unit_price` is the current Product `final_price`;
no price or stock snapshot is stored. `available` is true only when the Product
is active and current stock covers the full line quantity. Stock reductions,
zero stock, and deactivation never silently remove or resize an item.
`total_quantity` and `total_price` include all retained items, including
unavailable ones, while `has_unavailable_items` lets clients block or qualify
checkout UI.

Cart is purchase intent only. It does not reserve or decrement stock, freeze
prices, create Orders, perform checkout, call payments, or send notifications.
The authoritative checkout service is internal to the Orders/Payments workflow:
it locks Product rows, decrements stock, creates immutable Order/OrderItem
snapshots and reservations, and clears the captured Cart in one PostgreSQL
transaction.

## React storefront consumption

The storefront consumes catalogue, username/password signup/login, refresh/logout,
current-profile updates, password management, and owner-bound Cart endpoints.
POST/PATCH Cart responses replace its state; after a 204 DELETE it reloads Cart.
SMS signup/login controls remain disabled even when capability is available.
Account-phone verification, Order history, and checkout/Payment UI are not
implemented. Backend routes do not imply corresponding frontend controls. See
[Frontend](../frontend/README.md) for route/state ownership and
[Authentication](authentication.md#frontend-session-and-feature-availability)
for session restoration and password navigation.

## Orders

Authenticated customers can read only their own commercial history:

- `GET /api/v1/orders/`
- `GET /api/v1/orders/<order_uuid>/`

`order_uuid` is a UUID string, not an integer database ID. The list is newest
first. Status is `waiting_for_payment`, `processing`, `shipped`, `delivered`, or
`cancelled`; `cancellation_reason` is empty, `payment_failed`, or
`reservation_expired`. Amounts are two-decimal strings (totals allow up to 24
digits including decimal places); lifecycle timestamps can be null. No
StockReservation object is serialized: the deadline is exposed through
`reservation_expires_at`. See [Architecture](architecture.md#orders-stock-and-historical-authority)
for reservation transitions.

These endpoints are read-only. They expose immutable product, price, customer,
and shipping snapshots; they do not create a checkout, reserve stock, accept a
payment result, or mutate fulfillment. A foreign order UUID returns `404`.

Order creation is an internal trusted service reached through Payment
initialization. Existing Order decimal amounts are toman (`IRT`). New Orders
snapshot the exact server-owned `ORDER_SHIPPING_FLAT_RATE_IRT` value, whose
tracked default is `350000.00 IRT` (350,000 toman); clients cannot submit shipping.
`subtotal` is the sum of immutable OrderItem line totals and `total = subtotal + shipping_amount`.
Historical Order snapshots are not recalculated if configuration changes.

`GET /api/v1/orders/` uses the same page-number envelope as Products (default
12, maximum 100). Each result has `uuid`, `status`, `subtotal`,
`shipping_amount`, `total`, `reservation_expires_at`, and `created_at`.

`GET /api/v1/orders/<order_uuid>/` returns those fields plus
`customer_first_name`, `customer_last_name`, `customer_phone_number`,
`customer_email`, `shipping_title`, `shipping_full_address`,
`shipping_postal_code`, `cancellation_reason`, `processing_at`, `shipped_at`,
`delivered_at`, `cancelled_at`, and `items`. Each item contains
`product_uuid`, `product_name`, `product_sku`, `unit_price`, `quantity`, and
`line_total`. The UUID/name/SKU, customer/address data, and decimal amounts are
historical snapshots; neither endpoint substitutes current Product, profile,
or Address values.

Notifications add no public SMS endpoint. When enabled, only a verified
Payment transition that actually changes an Order to `PROCESSING` creates a
customer confirmation and one processing obligation for every active
superuser whose account has a valid canonical Iranian mobile number.
Superusers without a valid phone are intentionally skipped; ordinary staff do
not receive this alert. `PROCESSING` to `SHIPPED` creates one customer-shipment
obligation. Replayed transitions create none.

## Payments

| Method and full path | Access | Success |
| --- | --- | --- |
| `POST /api/v1/payments/initialize/` | Authenticated, active complete profile; Payment initialization throttle | 200, 201, or 202; safe envelope plus redirect guidance |
| `GET /api/v1/payments/<payment_uuid>/` | Authenticated owner; default DRF throttles | 200; safe envelope |
| `GET /api/v1/payments/callback/<provider>/` | Public, no JWT authentication; Payment callback throttle | Browser 303 or non-browser 202/204 |
| `POST /api/v1/payments/callback/<provider>/` | Same as GET callback | Same as GET callback |

`payment_uuid` is a UUID; `provider` is the registered provider's route slug.
There is no public Refund mutation endpoint.

Payment handlers return `503` while `PAYMENTS_ENABLED=False`; normal DRF
authentication, permission, and throttle checks still run before protected
handlers. Disabled operation is the tracked default because no production
provider adapter has been selected.

`POST /api/v1/payments/initialize/` requires JWT authentication, a complete
active profile, the fail-closed Payment throttle, and an
`Idempotency-Key: <UUID>` header. The JSON body contains exactly one of
`address_uuid` or `order_uuid`. Provider, amount, currency, user, callback URL,
return URL, and `shipping_amount` are rejected. A Payment amount is derived
only from the locked `Order.total`; no client field or independent shipping
calculation can alter it. New redirect-ready attempts return `201`,
completed replays return `200`, and pending attempts/replays return `202`.
A new attempt with no usable redirect also returns `202`; inspect its persisted
status rather than assuming every 202 means the same provider outcome. The
response contains safe `payment`, `order`, nullable `refund`, and
nullable `redirect_url` values. A `202` response also contains
`retry_after_seconds` and the same bounded value in the `Retry-After` header.
Initialization also requires a valid trusted client address derived from the
request peer/proxy policy. If that address cannot be determined, it returns a
safe `400` before any checkout, stock reservation, Payment, or provider side
effect.

`GET /api/v1/payments/<payment_uuid>/` is authenticated and owner-only;
foreign UUIDs return `404`. It omits provider sessions/transactions/receipts,
diagnostics, request IDs, IP addresses, and user agents.

The initialization body selects an owned address for new Cart checkout or an
existing owned Order eligible for payment. Malformed/missing UUID headers, neither/both source
fields, and any unknown body field return 400. Foreign/missing Order lookup is
404; invalid/foreign addresses and checkout-stock failures return 400 under
`checkout`. An incomplete profile is 403; service-level profile races may
include `code: profile_not_ready`.

Reuse a key with the same source to inspect an attempt. Do not generate fresh
keys merely because a response is pending. Key/source/owner conflicts, another
open checkout/attempt, and ineligible Orders return 409 with
`{"code": "payment_conflict", "detail": "<message>"}`.

For example, this request selects an owned address (all credentials/UUIDs below
are placeholders):

```http
POST /api/v1/payments/initialize/
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000

{"address_uuid": "d9428888-122b-4f09-b53e-7f3b20a5eabc"}
```

The safe Payment representation is:

```json
{
  "payment": {
    "uuid": "<payment-uuid>",
    "status": "redirect_ready",
    "amount": "350100.00",
    "currency": "IRT",
    "provider_requested_at": "<datetime-or-null>",
    "redirect_ready_at": "<datetime-or-null>",
    "verified_at": null,
    "failed_at": null,
    "manual_review_at": null,
    "created_at": "<datetime>",
    "updated_at": "<datetime>"
  },
  "order": {
    "uuid": "<order-uuid>",
    "status": "waiting_for_payment",
    "reservation_expires_at": "<datetime>"
  },
  "refund": null
}
```

When present, `refund` contains `uuid`, `status`, `reason`, `amount`,
`currency`, `created_at`, `refunded_at`, and `manual_review_at`.
Initialization responses add `redirect_url`; pending initialization responses
also add `retry_after_seconds`. Payment detail does not add either field.

`GET /api/v1/payments/callback/<provider>/` or
`POST /api/v1/payments/callback/<provider>/` is public but accepts only a
registered server-side provider. Callback parsing/validation belongs to the
adapter contract; no real adapter or provider-specific signature implementation
is registered here. The backend
verifies the identified existing provider session server-to-server. Browser
status text is never payment proof. Browser callbacks receive a `303` to the configured frontend result URL containing only
`payment_uuid`; client-supplied return URLs are ignored.

Non-browser callbacks return `202` while verification remains pending and
`204` after the callback has been handled without a pending operation. Both
responses have no payment-result body; neither is proof that a Payment was
captured. When enabled, an unknown provider or unknown provider session is 404;
invalid callback parsing/session shape is 400 under `callback`. Callback body,
query fields, and signature rules depend on the eventual adapter; there is no
universal client-supplied `success` contract.

Payment status values are `pending`, `redirect_ready`, `verifying`, `verified`,
`failed`, and `manual_review`. Refund status is `pending`, `processing`,
`refunded`, or `manual_review`, with reason `late_payment`, `duplicate_payment`,
or `amount_mismatch`. Inspect the owner-visible Payment and Order together;
a captured late/mismatched Payment can coexist with a cancelled Order and a
Refund obligation. A null refund does not promise that none can arise later.

## Status codes

- `200 OK` — successful reads, login, profile, logout, password-reset, Cart increment, Cart quantity-update operations, and an identical completed Payment initialization replay.
- `201 Created` — direct signup, OTP signup verification, product/image creation, a newly created CartItem, or a new redirect-ready Payment initialization.
- `202 Accepted` — a new Payment initialization has no usable redirect, or an attempt/callback is pending; initialization includes `retry_after_seconds` and `Retry-After`.
- `204 No Content` — product, product-image, or Cart item deletion, Cart
  clearing, and a handled non-browser Payment callback with no pending work.
- `400 Bad Request` — serializer validation, Cart stock limits, generic
  identity/OTP errors, invalid Payment callback input, or failure to derive a
  trusted client IP for Payment initialization.
- `401 Unauthorized` — missing, invalid, or stale JWT credentials on a protected endpoint; failed username/password authentication; or invalid/replayed refresh tokens.
- `403 Forbidden` — an authenticated non-staff user attempted a staff-only
  operation, a Payment initiator lacks a complete active profile, or a
  cookie-setting, refresh, or logout authentication request has a missing or
  untrusted Origin.
- `404 Not Found` — unknown or non-visible product/image, inactive or missing Cart-add Product, missing owned CartItem/Order/Payment, or unknown enabled callback provider/session.
- `303 See Other` — a browser Payment callback redirects to the configured result URL with only `payment_uuid`.
- `409 Conflict` — a Product is protected by commercial OrderItem history, or
  a Payment idempotency, active-checkout, eligibility, or in-progress-attempt
  conflict. Payment conflicts use the stable code `payment_conflict`.
- `429 Too Many Requests` — a configured throttle, temporary OTP lock, password-login lock, or active verification lease.
- `503 Service Unavailable` — authentication protection cannot access the security cache safely, an SMS-dependent authentication service is unavailable, or a Payment handler is disabled (`PAYMENTS_ENABLED=False`) or initialization cannot use its configured provider. The disabled-service behavior applies after its normal authentication, permission, and throttle checks.
