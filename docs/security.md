# Security

## Implemented controls

DRF defaults to `IsAuthenticated`; user-authentication routes explicitly use `AllowAny`. Product reads permit anonymous access, while product and image mutations require authenticated staff users. Public and authenticated non-staff catalogue reads share a response cache because their output is identical; staff bypass it because they may inspect inactive products. `Product.is_active` is catalogue visibility only and does not alter `User.is_active` account-state behavior.

Passwords use Django's hash API and one 12-character-minimum Django validator policy. Username and email values are case-insensitively unique at the database layer. The accompanying migration refuses to proceed if legacy case conflicts exist, preserving records for private operator remediation.

Simple JWT accepts Bearer access tokens. `POST /api/v1/users/token/refresh/` rotates refresh tokens and blacklists the superseded value. Tokens include Simple JWT's password-hash revocation claim: profile password changes and OTP resets blacklist all outstanding refresh tokens and reject previously issued access tokens. Logout blacklists only a submitted refresh belonging to the authenticated user. These controls intentionally invalidate tokens issued before the password-revocation claim was enabled.

Username/password failures remain generic for unknown, incorrect, inactive, and unusable-password accounts. Unknown and legacy-ambiguous paths execute a dummy hash before returning. Usernames are looked up case-insensitively without selecting an arbitrary legacy conflict.

## Throttling and security cache

The global DRF anonymous/authenticated throttles are supplemented by signup, password-login, and two OTP dimensions. Every OTP request and verification route applies independent limits keyed by canonical phone number and trusted client IP. Phone settings are `OTP_REQUEST_THROTTLE_RATE` and `OTP_VERIFY_THROTTLE_RATE`; IP settings are `OTP_REQUEST_IP_THROTTLE_RATE` and `OTP_VERIFY_IP_THROTTLE_RATE`.

OTP throttles, codes, failed-attempt counters, temporary locks, verification leases, and password-login guard state use only the `security` cache alias. It does not ignore errors: security-cache failures return 503 instead of allowing an unprotected request. The ordinary `default` cache is separate and may tolerate failures for catalogue caching. Production sets `DRF_NUM_PROXIES` to one because only host-managed Nginx can reach loopback Gunicorn; do not trust forwarded client IP headers in another topology without changing that setting.

Phone input is canonical ASCII `09[0-9]{9}` and OTP input is six ASCII digits. Invalid alternate digit sets or formatting are rejected before application logic. OTP state remains namespaced by `signup`, `login`, and `password-reset`. `OTP_EXPIRY_SECONDS`, `OTP_VERIFICATION_MAX_ATTEMPTS`, and `OTP_VERIFICATION_LOCK_SECONDS` control expiry and the separate per-phone verification lock. Verification compares with `secrets.compare_digest` and uses an atomic Redis lease so only one concurrent consumer succeeds. The multi-key sequence is not a Redis transaction.

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

## Configuration, logging, and transport

Runtime configuration is loaded from the ignored root `.env`. Production requires distinct Django and JWT signing keys; use at least 32 random bytes for the JWT key. Never put real values in tracked environment examples. Structured logs use allowlisted fields and redact common secret/PII patterns. Callers must not include passwords, OTPs, JWTs, credentials, raw phone numbers, email addresses, cache keys, or sensitive internal errors. Authentication and SMS-placeholder events use fixed generic names; system errors record an exception type, never an exception message or traceback.

## Verification and limitations

CI runs pytest with warnings as errors, Ruff, Bandit, Django checks, and migration-drift checks. The marked PostgreSQL/Redis suite covers persistent case-fold constraints, concurrent signup, Redis throttle keys, and concurrent OTP consumption.

- OTP delivery remains a Celery placeholder; no SMS provider is implemented.
- OTP values are cache values, not password hashes; Redis access and AOF copies must remain tightly restricted.
- Redis leases serialize consumption but do not make all verification keys one atomic transaction.
- The repository does not yet provide managed object storage or automated dependency-vulnerability monitoring.

Review security-sensitive changes for authorization, authentication, input validation, secret handling, cache failure, logging, uploads, concurrency, and database integrity. Report suspected vulnerabilities privately to the repository maintainer.
