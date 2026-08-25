# Security

## Implemented controls

DRF defaults to `IsAuthenticated`; user-authentication routes explicitly use
`AllowAny`. Product reads permit anonymous access, while product and image
mutations require authenticated staff users. Every Cart route explicitly
requires authentication but not profile completion, derives ownership from
`request.user`, and exposes no user or CartItem identifier in its URLs.
Public and authenticated non-staff catalogue reads share a response cache
because their output is identical; staff bypass it because they may inspect
inactive products. Cart responses are never cached. `Product.is_active` is
catalogue visibility only and does not alter `User.is_active` account-state
behavior.

Passwords use Django's hash API and one 12-character-minimum Django validator policy. Username and email values are case-insensitively unique at the database layer. These functional uniqueness constraints are declared directly in the users application's current initial migration.

Django Admin uses `is_staff` only to control admin-site login eligibility;
actual model access still requires Django model permissions. Delegated,
non-superuser staff may manage customer accounts but cannot view or modify
staff or superuser accounts or their addresses, assign groups or direct
permissions, or manage permission groups. Superusers retain those management
capabilities. The Cart admin is read-only and applies the same owner boundary:
delegated staff cannot inspect carts owned by staff or superusers. Admin
password changes and customer deactivation blacklist all outstanding refresh
tokens.

Simple JWT accepts Bearer access tokens. `POST /api/v1/users/token/refresh/` rotates refresh tokens and blacklists the superseded value. Tokens include Simple JWT's password-hash revocation claim: profile password changes and OTP resets blacklist all outstanding refresh tokens and reject previously issued access tokens. Logout blacklists only a submitted refresh belonging to the authenticated user. These controls intentionally invalidate tokens issued before the password-revocation claim was enabled.

The React storefront centralizes bearer-token handling. Its access token is
memory-only and its rotating refresh token uses `sessionStorage`; no component
logs or directly persists either token. `sessionStorage` limits persistence to
the browser session compared with `localStorage`, but any browser-readable
bearer token remains exposed to JavaScript after a successful XSS compromise.
Consequently this is a usability/security trade-off within the existing JWT
contract, not an HttpOnly-cookie security claim. A protected 401 shares one
in-flight refresh, retries once, and clears application authentication when
refresh fails. Safe internal-path validation prevents a Login return target
from becoming an external redirect.

Username/password failures remain generic for unknown, incorrect, inactive, and unusable-password accounts. Unknown and legacy-ambiguous paths execute a dummy hash before returning. Usernames are looked up case-insensitively without selecting an arbitrary legacy conflict.

## Throttling and security cache

The global DRF anonymous/authenticated throttles are supplemented by signup, password-login, and two OTP dimensions. Every OTP request and verification route applies independent limits keyed by canonical phone number and trusted client IP. Phone settings are `OTP_REQUEST_THROTTLE_RATE` and `OTP_VERIFY_THROTTLE_RATE`; IP settings are `OTP_REQUEST_IP_THROTTLE_RATE` and `OTP_VERIFY_IP_THROTTLE_RATE`. The default request limits are one request per phone and ten requests per IP each minute: a strict per-phone control that still accommodates shared NATs.

OTP throttles, codes, failed-attempt counters, temporary locks, verification
leases, the password-login guard, and password-login/signup throttle histories
use only the `security` cache alias. It does not ignore errors: security-cache
failures return 503 instead of allowing an unprotected request. The ordinary
`default` cache is separate and may tolerate failures for catalogue caching.
Production sets `DRF_NUM_PROXIES` to one because only host-managed Nginx can
reach loopback Gunicorn; do not trust forwarded client IP headers in another
topology without changing that setting.

Phone input is canonical ASCII `09[0-9]{9}` and OTP input is six ASCII digits.
Invalid alternate digit sets or formatting are rejected before application logic.
OTP state remains namespaced by `signup`, `login`, `password-reset`, and a
profile-phone purpose bound to the authenticated user's ID.
`OTP_EXPIRY_SECONDS`, `OTP_VERIFICATION_MAX_ATTEMPTS`, and
`OTP_VERIFICATION_LOCK_SECONDS` control expiry and the separate per-phone
verification lock. Verification compares with `secrets.compare_digest` and
uses an atomic Redis lease so only one concurrent consumer succeeds. Issuing a
new code does not reset failed attempts or an active lock, and a successful
verification consumes the code. The multi-key sequence is not a Redis
transaction.

`User.is_active` is reserved for account enablement and disablement; profile
progress never changes it. Profile completeness is derived from username,
verified phone number, email, names, and an address. `IsProfileComplete` is an
opt-in permission for future sensitive customer operations and is not a global
authentication gate. The authenticated profile-phone flow only stores a phone
after OTP success and uses a locked user row plus the unique database
constraint to reject ownership races.

Cart mutations lock the authenticated user's PostgreSQL row before the Cart
and CartItem. This serializes only one user's Cart, preventing duplicate lazy
Cart creation and lost same-item increments without a global lock or Product
row lock. Database uniqueness and quantity checks remain authoritative. Cart
does not reserve inventory, so stock may change immediately after Cart
validation; future Order/checkout code must perform the final stock lock and
decrement.

## Data and upload integrity

The custom user model requires active users to have a username or phone
number. Product discounts must be lower than regular price, fragrance volume
must be positive, introduction years cannot predate 1700, and optional
8–14-digit barcodes are unique. Application validation also rejects future
introduction years. A conditional unique constraint allows one primary image
per product. Ordered fragrance-note links enforce valid top/middle/base layers,
positive positions, and uniqueness of both note and position within each
product layer. Decimal validation uses `Decimal` bounds, avoiding float
coercion warnings. Category saves reject cycles. Product uploads are
staff-only and restrict MIME/content pairs, file size, dimensions, corruption,
decompression bombs, and generated filenames.
Each user has at most one Cart, each Product appears at most once in that Cart,
and CartItem quantity is at least one. Product deletion may cascade temporary
CartItems. Cart stores no price, stock, availability, status, or expiration
snapshot.

## Configuration, logging, and transport

Runtime configuration is loaded from the ignored root `.env`. Production requires distinct Django and JWT signing keys; use at least 32 random bytes for the JWT key. Never put real values in tracked environment examples. Structured logs use allowlisted fields and redact common secret/PII patterns. Callers must not include passwords, OTPs, JWTs, credentials, raw phone numbers, email addresses, cache keys, or sensitive internal errors. Authentication and SMS-placeholder events use fixed generic names; system errors record an exception type, never an exception message or traceback.

For local development Django allows only the documented Vite origins at ports
5173. Production Django is hosted at `shop.exonplus.ir` and allows the
`https://www.exonplus.ir` storefront origin. The public build-time
`VITE_API_BASE_URL` contains only the Django origin; `VITE_*` values must never
contain Django/JWT signing keys, database/Redis credentials, future payment
credentials, or VPN credentials. `api.exonplus.ir` is unrelated VPN/3x-ui
infrastructure and is not an allowed host, frontend API origin, or deployment
target for this application.

## Verification and limitations

CI runs pytest with warnings as errors, Ruff, Bandit, Django checks, and
migration-drift checks. The marked PostgreSQL/Redis suite covers persistent
case-fold constraints, concurrent signup, Cart creation/increment races and
unrelated-user lock isolation, Redis throttle keys, and concurrent OTP
consumption.

- OTP delivery remains a Celery placeholder; no SMS provider is implemented.
- OTP values are cache values, not password hashes; Redis access and AOF copies must remain tightly restricted.
- Redis leases serialize consumption but do not make all verification keys one atomic transaction.
- The repository does not yet provide managed object storage or automated dependency-vulnerability monitoring.

Review security-sensitive changes for authorization, authentication, input validation, secret handling, cache failure, logging, uploads, concurrency, and database integrity. Report suspected vulnerabilities privately to the repository maintainer.
