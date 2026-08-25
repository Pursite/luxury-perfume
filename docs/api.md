# API reference

## Conventions

All routes are under `/api/v1/`. Normal bodies are JSON. Send an access token for protected endpoints:

```http
Authorization: Bearer <access-token>
```

User routes begin `/api/v1/users/`; product routes begin `/api/v1/products/`;
Cart routes begin `/api/v1/cart/`. Examples with placeholder tokens, UUIDs, or
product values are illustrative unless their fields are explicitly listed
below.

## Users

| Method and path | Access | Request | Success |
| --- | --- | --- | --- |
| `POST /users/signup/` | Public; signup throttle | `username`, `password` | 201; `user.username` and `tokens.refresh`/`tokens.access` |
| `POST /users/signup/send-otp/` | Public; phone + IP OTP-request throttles | `phone_number` | 200; message and `expires_in` |
| `POST /users/signup/verify-otp/` | Public; phone + IP OTP-verification throttles | `phone_number`, `otp` | 201; message and tokens |
| `POST /users/login/userpass/` | Public; password-login throttle | `username`, `password` | 200; message and tokens |
| `POST /users/token/refresh/` | Public | `refresh` | 200; rotated `access` and `refresh` tokens |
| `POST /users/login/send-otp/` | Public; phone + IP OTP-request throttles | `phone_number` | 200; message and `expires_in` |
| `POST /users/login/verify-otp/` | Public; phone + IP OTP-verification throttles | `phone_number`, `otp` | 200; message and tokens |
| `POST /users/profile/phone/send-otp/` | Authenticated; phone + IP OTP-request throttles | `phone_number` | 200; generic message and `expires_in` |
| `POST /users/profile/phone/verify-otp/` | Authenticated; phone + IP OTP-verification throttles | `phone_number`, `otp` | 200; verified serialized user in `data` |
| `GET /users/profile/` | Authenticated | No body or user identifier | 200; current serialized user in `data` |
| `POST /users/profile/complete/` | Authenticated; requires a verified phone | `username`, `email`, `first_name`, `last_name`, `address` | 200; message and serialized user in `data` |
| `PATCH /users/profile/update/` | Authenticated | Any subset of `username`, `email`, `first_name`, `last_name`, `password`, `address` | 200; message and serialized user in `data` |
| `POST /users/logout/` | Authenticated | `refresh` | 200; logout message |
| `POST /users/password-reset/send-otp/` | Public; phone + IP OTP-request throttles | `phone_number` | 200; message and `expires_in` |
| `POST /users/password-reset/verify-and-reset/` | Public; phone + IP OTP-verification throttles | `phone_number`, `otp`, `password` | 200; message and tokens |

All user endpoint paths in this section are relative to `/api/v1/users/`.
`phone_number` must match ASCII `09[0-9]{9}`, such as `09123456789`; Unicode
digits and alternate formats are rejected. OTPs are exactly six ASCII digits.
Refresh responses rotate the submitted refresh token and blacklist its prior
value. Password changes invalidate older access and refresh tokens. Detailed
security behavior is in [authentication.md](authentication.md).

Usernames supplied by signup, profile completion, or profile update must be
5–150 ASCII letters, digits, or underscores.

`GET /users/profile/` always resolves the authenticated user and does not accept
a user ID. It returns `{"data": <serialized-user>}` and prefetches that user's
addresses in creation order.

The `address` accepted by profile completion has `title`, `full_address`, and optional `postal_code`. Profile update accepts the same shape; when the user already has an address it must include that address's owned `id`, then may include only the fields being changed. Without an ID, profile update creates an address only for a user that has none and requires `title` and `full_address`. The serialized user contains `id`, `phone_number`, `username`, `email`, `first_name`, `last_name`, `is_profile_complete`, and `addresses`; an address has `id`, `title`, `full_address`, and `postal_code`. Passwords, tokens, staff state, groups, and permissions are never present in this representation.

## Products

| Method and path | Access | Request / behavior | Success |
| --- | --- | --- | --- |
| `GET /products/` | Public | Lists active products | 200; paginated product list |
| `POST /products/` | Authenticated staff only | Product write fields | 201; product detail |
| `GET /products/<product_slug>/` | Public | Retrieves an active product; staff can retrieve inactive products | 200; product detail |
| `PUT /products/<product_slug>/` | Authenticated staff only | Complete product write fields | 200; product detail |
| `PATCH /products/<product_slug>/` | Authenticated staff only | Partial product write fields | 200; product detail |
| `DELETE /products/<product_slug>/` | Authenticated staff only | — | 204; no body |
| `POST /products/<product_slug>/images/upload/` | Authenticated staff only | Multipart form data | 201; image object |
| `DELETE /products/images/<image_id>/` | Authenticated staff only | `image_id` is an integer | 204; no body |

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

`volume_ml` must be positive. `discount_price`, when provided, must be lower
than `price`. `introduction_year` must be between 1700 and the current year.
`barcode` is distinct from `sku`; when present it must be unique and contain
8–14 ASCII digits. An empty barcode is stored as null so multiple products can
omit it. Existing products migrated from the former catalogue use the neutral
`unspecified` classification until staff curate them; new writes may also use
that explicit value.

Product-list output fields are `uuid`, `name`, `slug`, `sku`, `price`,
`discount_price`, `final_price`, `stock`, `concentration`, `target_audience`,
`fragrance_family`, `introduction_year`, `suitable_season`,
`suitable_usage_time`, `volume_ml`, `category`, `brand`, `primary_image`,
`is_featured`, and `created_at`. Detail adds `description`,
`country_of_origin`, `barcode`, `top_notes`, `middle_notes`, `base_notes`,
`is_active`, `images`, and `updated_at`. Each note summary has `uuid`, `name`,
and `slug`, and each layer array is in its persisted position order. Category
summaries have `uuid`, `name`, and `slug`; brand
summaries add `country`. An image object has integer `id`, `image`, `thumbnail`,
`is_primary`, and `display_order`.

The product `uuid` remains a stable response identifier but is not a URL lookup
value.

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
  layers, `min_price`, `max_price`, and boolean `in_stock` (`true` selects
  stock above zero; `false` selects zero stock).

A paginated response has this exact shape:

```json
{
  "count": 25,
  "total_pages": 3,
  "current_page": 1,
  "page_size": 12,
  "links": {"next": "<url-or-null>", "previous": null},
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

The server checks declared MIME type, decoded image format, MIME/content consistency, corruption, decompression-bomb warnings, a 5 MB maximum size, and a 6000 × 6000 maximum dimension. It generates a safe filename. The image ID returned by this endpoint is the integer needed for the image-delete route.

## Cart

Every Cart endpoint requires authentication but does not require a complete
profile. Cart ownership always comes from the access token; requests and URLs
never accept a user ID. There are no anonymous or session carts and no
pagination.

| Method and path | Request / behavior | Success |
| --- | --- | --- |
| `GET /cart/` | Read the current user's Cart; never creates one | 200; full Cart |
| `DELETE /cart/` | Clear all items; retain an existing empty Cart | 204; no body |
| `POST /cart/items/` | `product_slug`, `quantity`; add quantity to an existing item | 201 for a new item or 200 for an increment; full Cart |
| `PATCH /cart/items/<product_slug>/` | `quantity`; set the absolute owned-item quantity | 200; full Cart |
| `DELETE /cart/items/<product_slug>/` | Remove the owned item | 204; no body |

`quantity` must be at least 1. A POST product must currently be active, and
the resulting quantity may not exceed current stock. Missing and inactive POST
products both return 404. PATCH uses current stock and returns 404 when the
user does not own an item with that exact, case-sensitive Product slug.
Existing inactive items remain visible and may be patched when current stock
covers the requested quantity; they remain unavailable. Deleting or clearing
a missing Cart is respectively 404 for an item and idempotent 204 for the
whole Cart.

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
Future checkout/Order code must own authoritative stock locking, stock
decrement, and price snapshots.

## React storefront consumption

The Luxury Perfume application in `frontend/` consumes these contracts without adding
frontend-only API assumptions. Catalogue search, the compact audience,
concentration, fragrance-family and availability filters, ordering, and
pagination are sent to `GET /products/`; results are never authoritatively
filtered in browser memory. Public Product links use response `slug` values.
The Product Detail page renders the actual ordered `images`, `top_notes`,
`middle_notes`, and `base_notes` arrays.

Username/password signup uses `/users/signup/`, login uses
`/users/login/userpass/`, token renewal uses `/users/token/refresh/`, and
sign-out uses `/users/logout/`. Signup and Login establish the same centralized
frontend JWT session. The frontend sends the access token as Bearer
authentication and never sends user, Cart, or CartItem IDs. An unauthenticated
Add-to-Cart action redirects to Login with a safe internal return path instead
of intentionally generating a Cart 401.

The protected `/account` route reads `/users/profile/` and uses only
`PATCH /users/profile/update/` for changes. Personal saves send changed
`username`, `email`, `first_name`, and `last_name` fields. Address saves either
create the first address or include the explicit owned address `id`; returned
`data` replaces the displayed profile. Profile data and drafts remain in React
memory only. The page does not expose the backend password field and its phone,
password-reset, Orders, and Tickets actions are disabled and make no request.

The storefront displays disabled SMS signup and sign-in controls for future
orientation, but they do not call the API's OTP endpoints.

Cart POST and PATCH responses replace frontend Cart state. Because item and
Cart DELETE endpoints correctly return no body, the frontend follows them with
`GET /cart/` before updating the shared badge and page. It renders API decimal
strings and live availability fields; it does not calculate an authoritative
price, resize/delete unavailable lines, reserve stock, or attempt checkout.
The visible payment control is disabled and makes no request.

## Status codes

- `200 OK` — successful reads, login, profile, logout, password-reset, Cart increment, and Cart quantity-update operations.
- `201 Created` — direct signup, OTP signup verification, product/image creation, or a newly created CartItem.
- `204 No Content` — product, product-image, or Cart item deletion and Cart clearing.
- `400 Bad Request` — serializer validation, Cart stock limits, generic identity/OTP errors, or a logout refresh that is not owned by the requester.
- `401 Unauthorized` — missing, invalid, or stale JWT credentials on a protected endpoint; failed username/password authentication; or invalid/replayed refresh tokens.
- `403 Forbidden` — an authenticated non-staff user attempted a staff-only operation.
- `404 Not Found` — unknown or non-visible product/image, inactive or missing Cart-add Product, or missing owned CartItem.
- `429 Too Many Requests` — a configured throttle, temporary OTP lock, password-login lock, or active verification lease.
- `503 Service Unavailable` — authentication protection cannot access the security cache safely.
