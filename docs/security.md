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

Simple JWT accepts Bearer access tokens. `POST /api/v1/users/token/refresh/` reads a host-only, `HttpOnly`, Secure-in-production `exon_refresh_token` cookie at `/api/v1/users/`, rotates it, and blacklists the superseded value. Tokens include Simple JWT's password-hash revocation claim: profile password changes and OTP resets blacklist all outstanding refresh tokens and reject previously issued access tokens. Logout blacklists the cookie's refresh token when valid and expires the cookie, even when the access token is expired. Login, signup, OTP verification, password reset, refresh, and logout responses use `Cache-Control: no-store` and compatible no-cache headers.

The React storefront centralizes bearer-token handling. Its access token is
memory-only and its rotating refresh token is stored only in the persistent
`HttpOnly` cookie; no component logs or directly persists either token. Startup
silently refreshes once, protected 401s share one in-flight refresh and retry
only after receiving a non-empty access token. A 401 refresh is an authoritative
anonymous result; network, 429, and 5xx failures preserve the session as a
retryable restoration error. Safe internal-path validation prevents a Login
return target from becoming an external redirect.

Cookie-backed POST operations (refresh, logout, and token-issuing browser
flows) require an exact trusted `Origin` and explicit CORS allowlist. SameSite
Lax reduces cross-site submission, but Origin validation is retained as the
server-side CSRF defense because these DRF JWT views do not inherit
SessionAuthentication's automatic CSRF enforcement. OPTIONS is allowed so
trusted browser preflight can complete; actual mutation requests remain
fail-closed.

The protected Account page keeps profile responses and form drafts in React
memory only; it does not persist profile PII in `localStorage` or
`sessionStorage`. `GET /api/v1/users/profile/` derives ownership exclusively
from the access token, accepts no user identifier, and uses the safe user
output serializer. Disabled phone verification, password reset, Orders, and
Tickets controls have no route or API side effect.

Username/password failures remain generic for unknown, incorrect, inactive, and unusable-password accounts. Unknown and legacy-ambiguous paths execute a dummy hash before returning. Usernames are looked up case-insensitively without selecting an arbitrary legacy conflict.

## Throttling and security cache

The global DRF anonymous/authenticated throttles are supplemented by signup, password-login, catalogue-read, refresh, and two OTP dimensions. Public Product list/detail reads use the ordinary-cache `catalogue` scope (`PRODUCT_CATALOGUE_THROTTLE_RATE`, default `120/m`) so unrelated anonymous API traffic cannot exhaust catalogue availability. Product mutations retain the existing authenticated user throttle. Refresh uses the fail-closed security-cache `token_refresh` scope (`TOKEN_REFRESH_THROTTLE_RATE`, default `30/m`). Every OTP request and verification route applies independent limits keyed by canonical phone number and trusted client IP. Phone settings are `OTP_REQUEST_THROTTLE_RATE` and `OTP_VERIFY_THROTTLE_RATE`; IP settings are `OTP_REQUEST_IP_THROTTLE_RATE` and `OTP_VERIFY_IP_THROTTLE_RATE`. The default request limits are one request per phone and ten requests per IP each minute: a strict per-phone control that still accommodates shared NATs.

OTP throttles, codes, failed-attempt counters, temporary locks, verification
leases, the password-login guard, password-login/signup throttle histories, and
refresh throttles use only the `security` cache alias. It does not ignore
errors: security-cache failures return 503 instead of allowing an unprotected
request. The ordinary `default` cache is separate and may tolerate failures
for catalogue caching and catalogue-read throttling.
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
validation; Order checkout performs the final stock lock and decrement.

Orders are protected against price/status mass assignment: only server-side
services derive monetary snapshots and state transitions. Customer reads are
owner-filtered, address selection is owner-filtered under lock, and order UUIDs
are never authorization. Product and user commercial references use `PROTECT`;
catalogue removal must deactivate Products and users with Orders require a
future explicit retention/anonymization policy. Deletion services map those
constraints to domain errors so the API/Admin do not expose raw database errors.

Payments accepts no client price, currency, provider, merchant identity,
callback URL, or return URL. Initialization derives the owner from JWT and the
amount from a locked Order. Dedicated Payment throttles use the fail-closed
security cache. Callback data is only a lookup hint: capture is accepted only
after server-to-server provider verification, and Orders decides timeliness
under its row lock. Redirect destinations must be HTTPS and match a configured
host allowlist. A trusted, canonical initiator IP is mandatory before Payment
initialization can create an Order, reserve stock, or call a provider; missing
or malformed direct-peer/proxy information fails the request safely.

The application stores normalized financial identities, amounts, timestamps,
request correlation, and limited IP/user-agent evidence. It never stores or
logs PAN, CVV/CVC, PIN, raw card credentials, Authorization values, provider
secrets, or raw provider payloads. Payment IP/user-agent evidence is scrubbed
after 180 days by default. Forwarded client IPs are ignored unless the
immediate peer and proxy chain match configured trusted CIDRs.
Ordinary structured logs emit only fixed financial events and allowlisted
correlation identifiers; they never include IPs, user agents, provider
identities, raw provider data, credentials, or card data.

No real provider adapter or credential contract is present. Production checks
reject enablement with an unknown provider, unsafe URLs/redirect hosts,
non-`IRT` currency, or absent trusted-proxy policy. Card entry must remain on
the provider-hosted page after an adapter and retention policy are approved.

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

Runtime configuration is loaded from the ignored root `.env`. Production requires distinct Django and JWT signing keys; use at least 32 random bytes for the JWT key. Never put real values in tracked environment examples. Structured logs use allowlisted fields and redact common secret/PII patterns. Callers must not include passwords, OTPs, JWTs, credentials, raw phone numbers, email addresses, cache keys, provider message IDs, rendered SMS, or sensitive internal errors. SMS audit events use fixed generic names; system errors record an exception type, never an exception message or traceback.

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

- No real SMS provider adapter is implemented, so SMS remains disabled in production. The durable Order outbox records event type and recipient snapshot, never rendered message content; accepted delivery means provider acceptance, not handset receipt. Order text remains fixed server-controlled source text until a provider is selected and an approved-template strategy is separately reviewed. Processing alerts are limited to active superusers with valid account phones; missing or malformed superuser phones are skipped, and ordinary staff are not recipients. Non-idempotent ambiguous sends require manual review rather than an automatic duplicate attempt.
- OTP values are cache values, not password hashes; Redis access and AOF copies must remain tightly restricted.
- Redis leases serialize consumption but do not make all verification keys one atomic transaction.
- The repository does not yet provide managed object storage or automated dependency-vulnerability monitoring.

Review security-sensitive changes for authorization, authentication, input validation, secret handling, cache failure, logging, uploads, concurrency, and database integrity. Report suspected vulnerabilities privately to the repository maintainer.
