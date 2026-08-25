# Architecture

## Overview

Luxury Perfume is a Django 6 and Django REST Framework application. Its current
Django applications are `apps.users`, `apps.products`, `apps.cart`, and
`apps.lib`. The repository also contains an independent React customer
storefront under `frontend/`.

```text
luxury-perfume/
├── apps/
│   ├── lib/          # shared infrastructure
│   ├── cart/         # authenticated purchase-intent carts
│   ├── products/     # catalogue domain
│   └── users/        # identity and profile domain
├── config/           # Django, URL, WSGI, ASGI, and Celery configuration
├── docker/
│   ├── env/           # tracked environment templates
│   ├── Dockerfile
│   └── docker-compose*.yml
├── docs/
├── frontend/        # React/Vite Luxury Perfume customer storefront
├── manage.py
└── requirements/
    ├── requirements.txt
    └── requirements-test.txt
```

## Request layers

```text
HTTP request
    ↓
APIView
    ↓
Input serializer
    ↓
Service (mutation) or selector (read)
    ↓
Model / PostgreSQL
    ↓
Output serializer and HTTP response
```

- **Views** orchestrate HTTP: select permissions and throttles, validate serializers, call the domain layer, and return responses.
- **Serializers** validate and normalize request data and define output representations. Product upload serializers also validate image content.
- **Services** implement state-changing workflows such as signup, OTP handling, password reset, logout, product writes, image writes, and post-commit cleanup/queueing.
- **Selectors** contain reusable read queries, including case-insensitive username lookups and filtered product queries.
- **Models** define durable state and model-level invariants. PostgreSQL
  constraints add final protection for active-user identities,
  case-insensitive username/email uniqueness, product discount prices,
  positive fragrance volume, introduction-year bounds, unique barcodes, and
  primary product images, one Cart per user, one CartItem per Cart/Product,
  and positive CartItem quantities.

## Applications

### `apps.users`

Owns the custom user and address models, user serializers and views, selectors,
and services for username/password and phone/OTP authentication, password
reset, profile-phone verification, profile onboarding/update, and logout. Its
current-profile selector scopes the read to the authenticated user and
prefetches ordered addresses for the safe output serializer.
`is_active` is account state, while `is_profile_complete` is a derived customer
readiness property. The opt-in `IsProfileComplete` permission is available for
future sensitive operations but does not restrict ordinary authenticated use.
Profile-phone OTP state is bound to both the account and the candidate phone;
address edits lock and require an explicitly owned address ID. It queues the
Celery OTP task.

### `apps.products`

Owns fragrance products, categories, brands, reusable fragrance notes, and
product images. A product stores bounded concentration, target audience,
fragrance family, season, and usage-time values. Product types such as perfume
and Body Splash use the existing category hierarchy. One explicit
`ProductFragranceNote` through model reuses normalized notes for top,
middle/heart, and base layers while persisting a 1-based position.
Public catalogue reads are filtered through selectors and can be cached. The
same versioned response cache serves anonymous and authenticated non-staff
requests because their representations are identical; staff requests bypass it
because they may retrieve inactive product details. Product visibility uses
`Product.is_active`, independently of account-state `User.is_active`.
Products use immutable lowercase slugs as their public URL identifiers;
canonical UUID-shaped slugs are rejected so legacy UUID text cannot be
ambiguous with a slug. The stable product UUID remains in API representations
but is not used for product-addressed routes.
Product and image writes are staff-only at the API boundary. Product services
lock concurrent product updates and replace submitted note layers in one
transaction. Database uniqueness constraints prevent a duplicate note or
duplicate position within a product layer, while check constraints enforce
valid layers and positive positions. Category hierarchy validation prevents
cycles; image services schedule thumbnail generation after commit.
Product-image creation assigns a collision-resistant object key. API creation
owns an outermost database transaction; the admin inline reuses the same
lifecycle inside Django Admin's transaction and compensates stored originals
if that outer transaction rolls back.
Image deletion locks and reloads its rows before collecting file names, keeping
storage cleanup consistent with concurrent thumbnail work.

### `apps.cart`

Owns authenticated purchase-intent carts and CartItems. Views never accept a
user identifier: every read and mutation is scoped to `request.user`, and
incomplete profiles may use the Cart. Input serializers validate request
shape, services own synchronous mutations, and the selector returns current
Product and image data without per-item queries.

Cart stores only its owner and each Product/quantity pair. Product
`final_price`, stock, activity, and images are read live, so price changes are
visible on the next response and unavailable items remain in the Cart.
Mutations lock the user row, then Cart, then CartItem, serializing only one
user's Cart. This prevents duplicate first carts and lost increments without
locking Product rows. Clearing retains the empty Cart container; GET never
creates one. Cart has no Redis cache, Celery tasks, async paths, stock/price
reservation, checkout, Order, payment, or notification responsibility.

### `apps.lib`

Contains shared base models, cache helpers, the security-cache guards, logging helpers, pagination, permissions, throttles, and reusable catalogue-image validation. It is for cross-application or project-wide infrastructure, not domain-specific business logic.

## Background work

Celery is configured in `config/celery.py` and discovers application tasks.

- User OTP requests store the code in the security cache and queue `send_otp_sms_task`. The task currently logs a placeholder result; an SMS-provider client is not implemented.
- Product-image creation queues `generate_product_image_thumbnail` after the database transaction commits. The task creates a WebP thumbnail in a deterministic `by-image-id/<id>/` namespace that cannot collide with legacy flat thumbnail names; row locking and validation of any referenced thumbnail make Celery redelivery idempotent.

## Data, cache, and authentication

PostgreSQL stores durable users, addresses, fragrance catalogue records,
reusable note relations, product images, carts, and Simple JWT
outstanding/blacklist records. The users, products, and Cart applications each
have a current initial migration that defines their schema and constraints.
The repository does not contain legacy identity, fragrance-domain, or
ordered-note data migrations. The catalogue cache uses a versioned schema
namespace so stale representations cannot be reused.

Redis has two configured cache aliases with separate URLs:

- `default` uses `CACHE_REDIS_URL` for ordinary catalogue caching. Its
  versioned product list/detail responses are shared by anonymous and
  authenticated non-staff users, while staff bypass the shared cache. It is
  configured to ignore cache exceptions, so a cache failure can fall back to
  the database. Cart responses are never stored in this cache.
- `security` uses `SECURITY_REDIS_URL` for OTP codes, attempt counters, locks,
  leases, password-login guard and throttle state, signup-throttle state,
  refresh throttles, and OTP phone/IP throttle histories. Profile-phone codes
  use a purpose scoped to the authenticated user. It does not suppress
  exceptions; security-cache errors produce a 503 response instead of bypassing
  authentication protection. Catalogue-read throttling remains on the ordinary
  `default` cache with catalogue caching.

JWT authentication is the DRF default. The custom refresh serializer validates Simple JWT's password-hash revocation claim while locking the user row, then rotates and blacklists the submitted refresh. Password changes use that same lock, blacklist all outstanding refresh tokens, and invalidate earlier access tokens. See [authentication.md](authentication.md).

## Configuration and logging

`config.settings.base` loads the root `.env` file with `django-environ`. Docker Compose also uses that file for interpolation and injects it into the `web` and `celery` services. Copy either tracked environment-specific example to `.env` to select the Django settings module. Production requires Django and JWT signing keys, PostgreSQL, separate cache URLs, Celery URLs, host/origin policy, and transport-hardening values.

Settings configure JSON logging for container output rather than application
log files. Activity events use stdout; security and system events, plus Django
errors, use stderr. The logger category remains `activity`, `security`, or
`system`, so operational filtering does not depend on a filename.

`RequestIDMiddleware` generates an opaque ID for every HTTP request, returns
it as `X-Request-ID`, and scopes it to structured application logs as both
`request_id` and `correlation_id`. OTP enqueue events also record the Celery
`task_id`; while executing that task, the worker uses the task ID as its
correlation ID. Records contain only an allowlisted set of fields: timestamp,
level, logger/category, event, IDs, authenticated user ID, a safe route path,
and exception type. They never serialize request bodies, headers, query
strings, exception messages, passwords, OTP codes, JWTs, credentials, phone
numbers, or other sensitive PII.

## Testing

Pytest uses `config.settings.test`, which substitutes SQLite, separate
local-memory cache namespaces, eager Celery tasks, and in-memory email. The root
`conftest.py` clears every configured cache alias around each test. Coverage is
measured over production code with branch tracking, excludes tests and
migrations, and requires at least 85%.

```bash
venv/bin/python -m pytest
venv/bin/python manage.py check --settings=config.settings.test
venv/bin/python manage.py makemigrations --check --dry-run \
  --settings=config.settings.test
```

PostgreSQL row locking, case-insensitive identity constraints, concurrent
signup, concurrent first Cart creation and same-item increments, unrelated-user
Cart lock isolation, real transaction behavior, Redis security-cache state,
normalized phone/IP throttle keys, and concurrent OTP consumption are covered
by tests explicitly marked `integration`. `config.settings.integration` reads test service endpoints from
the environment; `docker/docker-compose.integration.yml` supplies isolated
local defaults, and the CI integration job supplies PostgreSQL 16 and Redis 7.

```bash
docker compose -f docker/docker-compose.integration.yml up -d --wait
venv/bin/python -m pytest \
  -o addopts="--strict-config --strict-markers" \
  -m integration --ds=config.settings.integration -q
docker compose -f docker/docker-compose.integration.yml down
```

Keep views thin, put mutations in services, reads in selectors, and enforce critical invariants in models and database constraints. Preserve existing route and response contracts unless an explicit compatibility decision says otherwise.

## Customer storefront

The React application is deployed independently of Django and preserves the
backend as the server-state authority:

```text
React route/page
    ↓
Domain API module
    ↓
Central request/JWT client
    ↓
Django API view → serializer → service/selector → PostgreSQL
```

`src/api/` owns URL construction, normalized API/network errors, Bearer access
headers, one shared refresh operation, and one retry after an authenticated
401. Pages do not scatter raw `fetch()` calls. `AuthContext` restores and ends
the browser session; `CartContext` loads and synchronizes the authenticated
owner's Cart. Product catalogue/detail data remains page-local because it is
not shared application state. Account profile data and independent form drafts
also remain page-local and memory-only; no profile context or browser-storage
PII cache is introduced.

Routes are `/` for the catalogue, `/products/:slug` for Product Detail,
`/login`, `/signup`, authenticated `/account`, authenticated `/cart`, and a
catch-all 404. The shared storefront layout owns the direct compact Header and
Persian development notice. Product filtering and
pagination use backend query parameters and browser URL state; the frontend
does not recreate authoritative catalogue filtering or price calculations.

The Account page reads the current user through the profile selector endpoint
and uses the existing profile-update service contract for mutations. Server
responses remain authoritative for fields and `is_profile_complete`. Phone
verification, password reset, Orders, and Tickets are visibly disabled and do
not have frontend routes or request handlers.

In development, Vite runs directly on the host at `127.0.0.1:5173` and proxies
relative `/api/` and `/media/` requests to Docker-published Django at
`localhost:8000`. PostgreSQL and Redis remain Docker-internal. Production
builds require the public build-time `VITE_API_BASE_URL` and emit static files
for host Nginx; there is no Vite server, Node runtime, or frontend Docker
service in production.
