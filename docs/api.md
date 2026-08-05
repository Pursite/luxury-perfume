# API reference

## Conventions

All routes are under `/api/v1/`. Normal bodies are JSON. Send an access token for protected endpoints:

```http
Authorization: Bearer <access-token>
```

User routes begin `/api/v1/users/`; product routes begin `/api/v1/products/`. Examples with placeholder tokens, UUIDs, or product values are illustrative unless their fields are explicitly listed below.

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
| `POST /users/profile/complete/` | Authenticated | `username`, `password`, `email`, `first_name`, `last_name`, `address` | 200; message and serialized user in `data` |
| `PATCH /users/profile/update/` | Authenticated | Any subset of `username`, `first_name`, `last_name`, `password` | 200; message and serialized user in `data` |
| `POST /users/logout/` | Authenticated | `refresh` | 200; logout message |
| `POST /users/password-reset/send-otp/` | Public; phone + IP OTP-request throttles | `phone_number` | 200; message and `expires_in` |
| `POST /users/password-reset/verify-and-reset/` | Public; phone + IP OTP-verification throttles | `phone_number`, `otp`, `password` | 200; message and tokens |

All user endpoint paths in this section are relative to `/api/v1/users/`.
`phone_number` must match ASCII `09[0-9]{9}`, such as `09123456789`; Unicode
digits and alternate formats are rejected. OTPs are exactly six ASCII digits.
Refresh responses rotate the submitted refresh token and blacklist its prior
value. Password changes invalidate older access and refresh tokens. Detailed
security behavior is in [authentication.md](authentication.md).

The `address` accepted by profile completion has `title`, `full_address`, and optional `postal_code`. The serialized user contains `id`, `phone_number`, `username`, `email`, `first_name`, `last_name`, `is_profile_complete`, and `addresses`; an address has `id`, `title`, `full_address`, and `postal_code`.

## Products

| Method and path | Access | Request / behavior | Success |
| --- | --- | --- | --- |
| `GET /products/` | Public | Lists active products | 200; paginated product list |
| `POST /products/` | Authenticated staff only | Product write fields | 201; product detail |
| `GET /products/<product_uuid>/` | Public | Retrieves an active product; staff can retrieve inactive products | 200; product detail |
| `PUT /products/<product_uuid>/` | Authenticated staff only | Complete product write fields | 200; product detail |
| `PATCH /products/<product_uuid>/` | Authenticated staff only | Partial product write fields | 200; product detail |
| `DELETE /products/<product_uuid>/` | Authenticated staff only | — | 204; no body |
| `POST /products/<product_uuid>/images/upload/` | Authenticated staff only | Multipart form data | 201; image object |
| `DELETE /products/images/<image_id>/` | Authenticated staff only | `image_id` is an integer | 204; no body |

`product_uuid` is a UUID. Product write fields are `category`, optional nullable `brand`, `name`, `slug`, `sku`, `description`, `price`, optional `discount_price`, `stock`, `abv`, `volume_ml`, optional `country_of_origin`, optional `vintage_year`, optional `ibu`, optional `taste_notes`, optional `serving_temp`, `is_active`, and `is_featured`. `category` and `brand` use their UUID primary keys; the category must be active. `discount_price`, when provided, must be lower than `price`.

Product-list output fields are `uuid`, `name`, `slug`, `sku`, `price`, `discount_price`, `final_price`, `stock`, `abv`, `volume_ml`, `category`, `brand`, `primary_image`, `is_featured`, and `created_at`. Detail adds `description`, `country_of_origin`, `vintage_year`, `ibu`, `taste_notes`, `serving_temp`, `is_active`, `images`, and `updated_at`. Category summaries have `uuid`, `name`, and `slug`; brand summaries add `country`. An image object has integer `id`, `image`, `thumbnail`, `is_primary`, and `display_order`.

### Product list query parameters

`GET /api/v1/products/` accepts:

- Pagination: `page` and `page_size` (default 12, maximum 100).
- Search: `search` across name, SKU, description, taste notes, brand name, and category name.
- Ordering: `ordering` with `price`, `created_at`, `abv`, `stock`, `name`, or `volume_ml`; prefix a field with `-` for descending order. Default: `-created_at`.
- Filters: UUID `category`, UUID `brand`, boolean `is_featured`, exact case-insensitive `country_of_origin`, `vintage_year`, `min_price`, `max_price`, `min_abv`, `max_abv`, and boolean `in_stock` (`true` selects stock above zero; `false` selects zero stock).

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

Anonymous product-list and detail responses use the default Redis cache when available. Cache behavior does not change visibility rules.

### Image upload

`POST /api/v1/products/<product_uuid>/images/upload/` requires `multipart/form-data` with:

- `image` — required JPEG, PNG, or WebP upload.
- `is_primary` — optional boolean, default `false`.
- `display_order` — optional non-negative integer, default `0`.

The server checks declared MIME type, decoded image format, MIME/content consistency, corruption, decompression-bomb warnings, a 5 MB maximum size, and a 6000 × 6000 maximum dimension. It generates a safe filename. The image ID returned by this endpoint is the integer needed for the image-delete route.

## Status codes

- `200 OK` — successful reads, login, profile, logout, and password-reset operations.
- `201 Created` — direct signup, OTP signup verification, product creation, and image upload.
- `204 No Content` — product or product-image deletion.
- `400 Bad Request` — serializer validation, generic identity/OTP errors, or a logout refresh that is not owned by the requester.
- `401 Unauthorized` — missing, invalid, or stale JWT credentials on a protected endpoint; failed username/password authentication; or invalid/replayed refresh tokens.
- `403 Forbidden` — an authenticated non-staff user attempted a staff-only operation.
- `404 Not Found` — unknown or non-visible product/image.
- `429 Too Many Requests` — a configured throttle, temporary OTP lock, password-login lock, or active verification lease.
- `503 Service Unavailable` — authentication protection cannot access the security cache safely.
