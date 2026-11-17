# Architecture

## System overview

Luxury Perfume has a Django REST Framework backend and an independent
React/Vite customer storefront. The backend owns identity, catalogue data,
Cart state, checkout snapshots, stock reservations, and financial/delivery
workflows. PostgreSQL is the durable source of truth. Redis supplies caches,
temporary authentication protection, and Celery transport/results.

The repository defines a development Compose stack and a single-VPS production
layout. It does not establish that a particular host is deployed or operational.
Provider-independent Payment/Refund and SMS logic exists, but no real Payment
or SMS adapter is registered; those subsystems are disabled by default.

```text
Browser → React route → domain API client → Django view
                                              ↓
                                      serializer validation
                                              ↓
                                  service (write) / selector (read)
                                              ↓
                                          PostgreSQL

Committed workflows → Celery broker → worker → database/storage/provider work
Celery Beat → periodic recovery tasks → database-authoritative due records
```

The asynchronous path is used where implemented; Cart writes stay synchronous.
A provider call is not part of a PostgreSQL transaction or a delivery guarantee.

## Request layers and application boundaries

| Layer | Responsibility |
| --- | --- |
| Views | HTTP methods, authentication/permissions/throttles, serializer invocation, response/status mapping |
| Serializers | Input shape, normalization and validation; explicit output representations |
| Services | Meaningful mutations, transaction and lock boundaries, lifecycle transitions, post-commit work |
| Selectors | Reusable, owner/visibility-scoped reads and deliberate related-object loading |
| Models and constraints | Persisted structure, model validation, database uniqueness/check/relationship protection |

This is a repository convention, not a requirement to wrap every simple query
in another abstraction. Views coordinate domain work rather than owning it.
Database constraints complement validation because serializer checks alone
cannot protect concurrent writes or direct ORM callers.

### Domain ownership

| Application | Owns | Boundary |
| --- | --- | --- |
| `apps.users` | Users, addresses, profiles, credentials, OTP challenges, JWT issuance/revocation | Users OTP delivery is separate from Order notifications |
| `apps.products` | Products, categories, brands, ordered fragrance notes, images, catalogue queries/cache | Product visibility and stock are server-owned |
| `apps.cart` | One owner-bound Cart and Product/quantity lines | Purchase intent; no stock or price reservation |
| `apps.orders` | Checkout snapshots, StockReservations, expiry/cancellation and fulfillment transitions | Sole authority for Order and reservation lifecycle |
| `apps.payments` | Payment attempts, provider verification, reconciliation, full Refund obligations | Calls Orders services; does not independently rewrite Order/stock state |
| `apps.notifications` | Durable Order-SMS obligations, delivery claims and retry/manual-review state | Does not change Order, Payment, Refund, or stock state |
| `apps.lib` | Shared cache, security, permissions, logging, pagination, upload validation, task and SMS primitives | Shared infrastructure rather than domain workflow ownership |

API route groups are defined in [`config/urls.py`](../config/urls.py).
Notifications has no public API. See [API](api.md) for endpoint contracts.

## Persistence and integrity

### PostgreSQL and validation boundaries

Durable records include users/addresses, catalogue relations and image metadata,
Cart lines, Order/OrderItem/StockReservation records, Payment/Refund evidence,
SMS outbox rows, `OTPChallenge`, and Simple JWT outstanding/blacklist records.
Uploaded file bytes remain outside PostgreSQL.

| Domain | Examples of database protection |
| --- | --- |
| Users | Active account requires username or phone; phone uniqueness; conditional case-insensitive username/email uniqueness |
| Products | SKU/slug/UUID/barcode uniqueness, nonnegative stock, discount below regular price, positive volume, introduction-year lower bound, one primary image, unique note/position per layer |
| Cart | One Cart per owner, one Product per Cart, quantity at least one |
| Orders | User/idempotency-key uniqueness, one waiting Order per user, nonnegative totals and `total = subtotal + shipping_amount`, line-total equations, reservation/status/timestamp consistency |
| Payments/Refunds | Provider identity uniqueness, one open attempt and one applied Payment per Order, one full Refund obligation per Payment, state/evidence/lease consistency |
| Notifications | Unique customer Order/event and owner Order/event/recipient obligations, provider-message identity uniqueness, recipient/event and lifecycle consistency |

Not every validation rule is a database constraint. Product price positivity,
future-year rejection, barcode format, category-cycle validation, and public
slug format/immutability rely on the supported validation/service/Admin paths.
Arbitrary ORM writes or bulk updates can bypass those paths. Database constraints
remain the final protection for the invariants actually declared there.

Commercial references protect users and Products from deletion through Order
history. Deleting a source Address clears its live foreign key while preserving
the Order's source-address UUID and shipping snapshot. Historical snapshots are
not recalculated from current profile, catalogue, or shipping configuration.

### Migration state

The current domain migration inventory is deliberately small:

- Users has `0001_initial` and
  [`0002_otpchallenge`](../apps/users/migrations/0002_otpchallenge.py). The latter
  adds durable scope, generation, expiry, and redemption state; it does not store
  OTP codes or recipient phone fields in the challenge row.
- Products, Cart, and Orders currently have `0001_initial`.
- Payments additionally has `0002_manual_review_stops_automatic_reconciliation`.
- Notifications additionally has
  `0002_remove_smsdelivery_notifications_order_event_unique_and_more`, adding
  recipient-user identity and the separate customer/owner uniqueness rules.

These files describe the checked-in migration history, not an automatic upgrade
strategy for an older installation. Existing production schema/history
reconciliation remains an operator-reviewed concern; see [Deployment](deployment.md).

### Redis and cache separation

Development and production use one Redis instance with separate logical databases:

| Setting/alias | Template database | Role and failure policy |
| --- | --- | --- |
| `CACHE_REDIS_URL` / `default` | `/0` | Catalogue response caching and ordinary DRF/catalogue throttles; cache exceptions may be ignored where configured |
| `SECURITY_REDIS_URL` / `security` | `/1` | OTP codes/generations, attempts, locks, leases, password-login guard, and custom security-throttle history; protection failures return 503 |
| `CELERY_BROKER_URL` | `/2` | Task transport, including sensitive OTP task payloads |
| `CELERY_RESULT_BACKEND` | `/3` | Task results with configured expiry |

Logical databases separate key spaces, not capacity, availability, or access
control. Shared Redis uses AOF with `appendfsync everysec` and `noeviction`.
Persistence supports restart recovery but is neither a backup nor a distributed
transaction with PostgreSQL. See [Security](security.md) for the trust boundary
and [Deployment](deployment.md) for capacity/retention considerations.

## Identity, OTP, and session architecture

Users retain display casing for trimmed username/email identities while lookup
and uniqueness are case-insensitive. `is_active` controls account access;
`is_profile_complete` is derived from customer details and an address. Incomplete
profiles may use normal authenticated endpoints, including Cart. Payment
initialization additionally requires an active complete profile.

Direct username/password signup and login issue Simple JWT sessions. Dedicated
services separate authenticated password change, initial password setup for
eligible OTP-only accounts, and SMS recovery for existing password accounts.
Profile updates reject credential changes. Authenticated profile-phone APIs
attach a phone only to the requesting account after verification, while it has
no phone already.

### Durable OTP redemption and temporary Redis state

[`OTPVerificationGuard`](../apps/lib/security_cache.py) coordinates two stores:

| Store | State |
| --- | --- |
| PostgreSQL `OTPChallenge` | HMAC-derived scope primary key, generation UUID, expiry, redeemed timestamp |
| Redis security cache | Code plus matching generation, TTL, failed-attempt counter, lockout and short admission lease |

Scopes include purpose and phone. `signup`, `login`, and `password-reset` have
distinct purposes; `password-set:<user-id>` and `profile-phone:<user-id>` also
bind the scope to the authenticated account. Initial setup uses the account
phone; profile-phone verification uses the candidate phone.

The implemented sequence is:

1. **Issue/resend:** create/find and lock the challenge row; rotate its generation,
   set its expiry, clear its redemption timestamp, and write the generation/code
   pair to Redis with a TTL. Resend does not reset the existing attempts/lockout
   keys. It avoids repeating the immediately active cached code.
2. **Verify:** acquire a short token-owned Redis lease to reduce overlapping work,
   then lock the challenge in a database transaction. Recheck lockout, database
   expiry/redemption, cached generation, and code using constant-time comparison.
3. **Apply:** run the success callback inside that transaction. Account changes,
   token records where issued/revoked, and `redeemed_at` commit together. Relevant
   callbacks lock and revalidate the user; signup additionally relies on identity
   uniqueness when creating a new account.
4. **Clean up:** after commit, lock/recheck the challenge before deleting the
   matching generation's cache state. Cleanup does not remove a newer resend.
   Lease release compares ownership atomically in Redis.

The PostgreSQL lock/redemption is authoritative for committed success. Lease
expiry does not replace that protection. If the success callback or database
commit fails, redemption and domain writes roll back and the unchanged code can
be retried while valid. Cleanup failure after success leaves redeemed database
state, so leftover Redis values cannot authorize a second success for that
generation.

There is no distributed transaction: a Redis write can survive a PostgreSQL
issuance rollback, or Redis state can disappear independently. Missing or
mismatched generations fail closed and require reissuance. Post-commit SMS task
publication/delivery is another failure boundary, not proof that the user
received a code. The Users task sends through the shared transport and has no
durable Notification outbox row. See [Authentication](authentication.md) for the
full flows and [Security](security.md#otp-protection-and-cross-store-limits)
for limits and controls.

### JWT ownership

The backend issues a bearer access token and a rotating refresh token. Browser
responses expose only access tokens in JSON; refresh lives in a host-only
HttpOnly cookie. The React access token is memory-only. Refresh locks the user
and validates password state before rotation/blacklisting. Password change/setup
and recovery revoke old refresh sessions and invalidate access tokens tied to
the previous password state. Logout blacklists the supplied refresh token and
expires its cookie; it is not an access-token blacklist.

## Catalogue and image lifecycle

Products use an internal integer key, a stable response UUID, and an immutable
lowercase public slug. UUID-shaped slugs are rejected by validation; product
URLs use slugs. Categories represent product types; ordered through-model rows
represent top, middle/heart, and base fragrance-note layers.

[`apps/products/selectors.py`](../apps/products/selectors.py) joins Category/Brand
and prefetches a ranked representative image for each list row. Detail queries
load images and ordered note links. Filtering/search/ordering and pagination
remain server-side. Anonymous and authenticated non-staff reads share the same
versioned catalogue response cache; staff bypass it because they may retrieve
inactive product details. Cart and owner-specific data are not cached there.
Signals and service writes invalidate catalogue namespaces after commit.

Image metadata and storage cannot commit atomically. The supported API/Admin
paths validate uploads and use collision-resistant original object names. API
creation owns an outermost database transaction; the Admin inline participates
in Admin's transaction and compensates newly stored originals on rollback.
Primary-image changes lock the Product and use a conditional uniqueness constraint.

Thumbnail work is queued after commit using an image ID, not file bytes. The
worker locks the image row, validates/reuses an existing WebP derivative, or
creates a bounded WebP at a deterministic `by-image-id/<id>/` path. Missing rows
are harmless and retries/redelivery reuse valid referenced data. Deletion reloads
locked rows and defers unreferenced-file cleanup until commit. Cleanup failures
are logged and can leave orphaned files; reference checks favor preserving valid
data over aggressive deletion. A failed thumbnail enqueue is logged rather than
turning a committed upload into a failed HTTP response; no periodic thumbnail
recovery sweep is configured.

## Cart, checkout, and financial workflows

### Cart: live purchase intent

Cart stores owner plus Product/quantity pairs, without price, stock, or expiry
snapshots. Reads resolve current price, availability, and images and never create
a Cart. Unavailable lines remain visible. Mutations are synchronous transactions
that lock user → Cart → CartItem, serializing one owner's writes without a global
Cart lock. Product stock is read without a Product lock because Cart does not
reserve inventory. Clearing retains an existing empty Cart.

### Orders: stock and historical authority

Payment initialization can invoke the internal Orders checkout service; customer
Order endpoints expose only owner-filtered reads. New checkout locks/revalidates
the user, verifies an owned address, locks Cart, then locks Product rows in
ascending numeric PK order and the captured CartItems. It limits checkout
to 100 distinct products, checks current activity/stock, and atomically:

- creates immutable customer/address/Product/price snapshots;
- snapshots the exact validated `ORDER_SHIPPING_FLAT_RATE_IRT` as shipping;
- calculates `subtotal` and `total = subtotal + shipping_amount`;
- creates an ACTIVE reservation per OrderItem and decrements available stock;
- clears only the captured CartItems.

The tracked shipping default is exact `350000.00 IRT` (350,000 toman).
User/idempotency-key replay returns stored snapshots; changing shipping
configuration does not rewrite history. A user can have at most one waiting
Order. Checkout reconciles an expired unswept waiting Order in its own committed
transaction before attempting its replacement.

`Product.stock` is available-to-sell stock. Orders use one 15-minute
`reservation_expires_at` deadline; reservations have no independent quantity or
expiry field. Order transition services lock Order, then ordered Products,
items, and reservations. On-time verified payment consumes ACTIVE reservations
without another stock decrement. Unpaid expiry/failure releases ACTIVE
reservations and restores their immutable line quantities once. At or after the
deadline, verification cannot reactivate a cancelled Order; it records a late
payment outcome. Admin fulfillment uses service-backed processing → shipped →
delivered transitions.

### Payments and Refunds: external evidence and obligations

Payments owns attempts against an Order, not checkout stock rules. Initialization
accepts an owned Order or address plus an idempotency UUID, requires a canonical
initiator IP, and derives the immutable amount only from the locked `Order.total`.
Amounts are decimal toman (`IRT`); provider-specific unit conversion belongs in
the adapter.

Claim/provider/finalization phases keep provider network I/O outside the local
claim transactions. Verification finalization locks Order before Payment and
calls Orders transitions. Callback/browser input is a lookup hint; a valid
server-to-server capture result is the financial evidence. Payment identity and
application constraints prevent the same capture from funding multiple Orders
or multiple Payments from funding one Order.

Late, duplicate, or amount/currency-mismatched captures remain financial facts
and create a full captured-amount Refund obligation. Refund execution claims
Payment/Refund state, calls the provider outside its claim transaction, and
checks its operation token before finalization. Payment/Refund UUIDs provide
stable provider idempotency references; the eventual adapter must honor the
contract. Reconciliation handles unresolved attempts; `MANUAL_REVIEW` is still
an open attempt for uniqueness but has no automatic lease/due reconciliation
time until explicitly rearmed. Audited superuser actions handle financial
recovery and externally completed Refund evidence.

### Notifications: durable delivery obligations

When SMS is enabled, Order transitions insert outbox obligations inside the
Order transaction: processing creates customer confirmation plus an owner alert
for each active superuser with a valid account phone; shipping creates a customer
shipment notice. Missing/malformed superuser phones are skipped; ordinary staff
are not recipients. When SMS is disabled, those event functions create no new
rows; enabling it later does not backfill those events.

Outbox uniqueness prevents duplicate logical obligations. After commit, workers
receive only delivery IDs. Publication failure leaves a due row for the periodic
sweeper. The worker claims/commits a delivery lease, performs provider I/O without
holding the claim lock, then finalizes only if its token still owns the operation.
States are `PENDING`, `SENDING`, `SENT`, `FAILED`, and `MANUAL_REVIEW`.

Known safe transport failures and ambiguity with an idempotent provider use
bounded exponential backoff/jitter. Rejection is terminal; non-idempotent
ambiguity, stale non-idempotent claims, protocol/configuration failures, or
exhausted attempts require manual review. `SENT` means provider-accepted, not
handset-delivered. The row retains recipient/evidence but not rendered SMS text;
fixed server-controlled templates are rendered at send time.

## Concurrency and recovery boundaries

Locks are workflow-specific rather than one universal lock hierarchy. Examples:

| Workflow | Relevant serialization |
| --- | --- |
| OTP success | Challenge row, then user where required by its callback; durable redemption in the same transaction |
| Profile/address mutations | User before owned address; Admin address reassignment locks affected owners |
| Cart | User → Cart → CartItem; Product reads remain live/unreserved |
| Checkout | User/existing Order, owned address/Cart, ordered Products, captured CartItems |
| Order transitions | Order → ordered Products → OrderItems → reservations |
| Payment verification finalization | Order before Payment/current related attempt |
| Refund execution | Payment before Refund; operation token guards finalization |
| SMS delivery | Delivery-row claim plus operation-token check after external I/O |

These mechanisms address tested races and durable invariants, not every possible
caller or failure. Direct writes must preserve the owning service contract.
External side effects cannot be rolled back by PostgreSQL; uncertainty needs
reconciliation or manual review rather than a claim of exactly-once delivery.

## Asynchronous processing

[`config/celery.py`](../config/celery.py) discovers tasks and loads Django settings.
JSON serialization, late acknowledgements, and rejection on worker loss make
retry/redelivery relevant. Individual tasks define retryable errors and limits;
a global retry setting is not automatic retry for every exception.

`transaction.on_commit()` prevents implemented enqueue paths from running before
their data commits. It does not atomically commit a broker message with the
transaction. Notifications has durable due rows to recover failed publication;
OTP sending and thumbnail enqueueing do not have that same outbox guarantee.

One Beat process schedules the following tasks from shared settings:

| Schedule | Interval | Responsibility |
| --- | --- | --- |
| `orders-sweep-expired-reservations` | 60 seconds | Queue up to 100 expired waiting Orders |
| `payments-sweep-reconcilable` | 60 seconds | Due pending/redirect-ready/verifying attempts; excludes manual review |
| `payments-sweep-pending-refunds` | 60 seconds | Due pending/stale processing Refunds |
| `payments-scrub-audit-metadata` | 24 hours | Expired Payment IP/user-agent evidence |
| `notifications-sweep-due-sms-deliveries` | 60 seconds | Due pending/stale sending rows while SMS is enabled |
| `notifications-scrub-expired-sms-recipients` | 24 hours | Expired terminal recipient snapshots while SMS is enabled |

Database deadlines and lifecycle state remain authoritative when Beat, Redis,
or workers are delayed. A delayed expiry task does not extend a reservation.

## Frontend integration

React Router defines catalogue, slug-addressed product detail, login, signup,
`/forgot-password`, protected `/account` and `/cart`, and a not-found route.
The central API client handles URLs, JSON/errors, bearer headers, one shared
in-flight refresh and one protected-request retry. Web Locks serialize
cookie-session operations across tabs where supported.

Auth Context restores/adopts/ends sessions. Refresh 401 means anonymous; network,
429, and server failures expose a retryable restoration state. Cart Context
mounts its stateful provider only when authenticated, serializes client mutations,
and replaces state with backend responses; DELETE is followed by a GET.
Backend owner checks remain authoritative regardless of route guards.

Catalogue/profile data and form drafts remain page-local and memory-only.
Account provides separate personal/address and password forms. Password change
and eligible initial setup clear the old session and navigate to Login;
SMS recovery adopts its replacement session and navigates to Account.
Initial setup/recovery are implemented but capability-gated. SMS login/signup,
phone verification, customer Orders/Tickets, checkout, and payments remain
unavailable in the current UI. See the [frontend guide](../frontend/README.md).

## Runtime and release topology

| Concern | Development | Production layout |
| --- | --- | --- |
| Django | Source-mounted `runserver`, loopback host port | Gunicorn from published application image, loopback upstream |
| React | Host Vite server with API/media proxy | Static build served by host-managed Nginx |
| PostgreSQL/Redis | Internal Compose services `db`/`redis`, named volumes | Internal services with persistent volumes |
| Worker/Beat | Source mounts and separate processes | Same published image as Django, separate services, one Beat |
| Files | Checkout media/static paths | Persistent host bind mounts shared with application/Nginx as needed |
| Edge/TLS | Local development HTTP | Host Nginx/TLS managed outside Compose |

The final Python image runs as UID/GID `10001`. Compose publishes only Django
to loopback in both layouts; Host Python cannot resolve/reach the private
services simply by activating a virtual environment. See [Development](development.md).

Production configuration loads the private root `.env`. CI builds/tests the
frontend and backend and validates release artifacts; matching SHA images are
published after the complete gate on `main`. The frontend image is a scratch
filesystem carrier, never a running Node service. Manual CD resolves image
digests, runs checks/migrations/static collection, checks web readiness and
worker/Beat stability, then activates the validated frontend symlink. It is not
a fully atomic cross-service/database deployment and does not reverse migrations
on rollback. See [Deployment](deployment.md) for runtime operations and [CI/CD](ci-cd.md) for pipeline and release orchestration.

The public health endpoints distinguish process responsiveness, app-registry
startup, and database/security-cache readiness. They do not establish complete
schema, worker, or provider health. The shared development health-check Host
mismatch is documented in [Troubleshooting](troubleshooting.md#health-status-and-the-development-host-mismatch).

## Verification and design trade-offs

The default backend suite uses SQLite/LocMem and eager Celery; real PostgreSQL/
Redis tests exercise selected transaction, constraint, lock, and security-state
races. Frontend Vitest uses jsdom and mocked APIs. CI also checks lint, static
security patterns, migration drift, production Compose, final-image translations,
and frontend release structure. See [Testing](testing.md) for commands and limits.

The design keeps synchronous domain invariants in PostgreSQL and defers expensive
or recoverable work. Its current limits include:

- No real registered SMS or Payment provider; adapter contracts and fake-provider
  tests do not establish live delivery, capture, or Refund behavior.
- One VPS and one shared Redis instance; logical databases do not provide
  independent failure or resource isolation.
- Non-transactional storage and broker publication can leave orphaned files or
  unqueued work; recovery coverage differs by workflow.
- No repository-managed host monitoring/alerting, backup scheduling/storage, or
  verified restore automation. Volumes and AOF are not backups.
- No managed object-storage integration or automated dependency-vulnerability
  monitoring platform configured here.
- Existing-installation migration reconciliation and provider-specific operational
  validation require separate review.

Human-readable backend messages support `en`/`fa`; JSON keys, enum values,
URLs, task/cache/audit identifiers, and Product content remain stable. The React
UI remains English apart from its Persian development notice. These boundaries
allow presentation changes without changing machine contracts.
