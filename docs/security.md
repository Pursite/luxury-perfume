# Security

## Implemented controls

DRF defaults to `IsAuthenticated`; user-authentication endpoints explicitly use `AllowAny`. Product list/detail reads explicitly permit anonymous access, while product and product-image mutations require an authenticated staff user.

Passwords use Django's password hash API. OTP-created accounts receive unusable passwords. Simple JWT accepts Bearer access tokens and enables refresh-token rotation and blacklist-after-rotation; logout blacklists the supplied refresh token. A previously issued access token remains valid until expiry.

Username/password failures use one generic error for unknown users, bad or unusable passwords, inactive accounts, and ambiguous case-conflicting legacy usernames. Username lookup and availability checking are case-insensitive, while stored casing is retained.

## Throttling and security cache

DRF throttles anonymous and authenticated requests globally, plus dedicated `otp`, `otp_verify`, `signup`, and `login` scopes. OTP request/verification throttles are keyed by submitted phone number when present; signup and password-login throttles use the DRF anonymous identifier.

The `security` Redis cache alias stores OTP codes, purpose-specific failed-attempt counters, temporary locks, verification leases, and username/IP-scoped password-login failure state. It does not ignore cache errors: authentication-sensitive operations fail closed with a 503 response when this state cannot be safely accessed. The ordinary `default` cache is separate and configured to tolerate cache errors for non-security catalogue caching.

OTP codes expire after `OTP_EXPIRY_SECONDS`; their state is isolated by the `signup`, `login`, and `password-reset` namespaces. Invalid verification attempts are tracked until expiry, reaching `OTP_VERIFICATION_MAX_ATTEMPTS` creates an `OTP_VERIFICATION_LOCK_SECONDS` temporary lock, and a successful verification removes the code and related state. OTP comparison uses `secrets.compare_digest`.

A five-second cache lease is acquired before OTP verification. It reduces concurrent-replay risk and returns 429 when another verification is in progress. It is not a fully atomic Redis transaction.

Password-login failures are scoped to normalized username plus client IP. `PASSWORD_LOGIN_MAX_ATTEMPTS` failures set a `PASSWORD_LOGIN_LOCK_SECONDS` temporary lock; a successful login clears only the matching scope.

## Data and upload integrity

The custom user model requires active users to have a username or phone number; this is checked by model validation, its manager, and a database check constraint. Product discounts must be lower than regular prices, and a conditional unique constraint allows only one primary image per product. Category validation prevents a category becoming its own ancestor during normal model saves.

Product uploads are staff-only and use multipart parsers. JPEG, PNG, and WebP are the only allowed MIME/content pairs. The validator limits files to 5 MB and images to 6000 × 6000 pixels, decodes and verifies image content with Pillow, rejects corrupt and decompression-bomb inputs, and normalizes generated filenames.

## Configuration, logging, and transport

Django loads the root `.env` file with `django-environ`, and Docker Compose uses that same ignored file for interpolation and injects it into the `web` and `celery` services. Copy the appropriate tracked example to `.env`; examples contain only non-production values or placeholders, never production credentials. Production requires a dedicated `JWT_SIGNING_KEY`, separate from `SECRET_KEY`, as well as host/origin, PostgreSQL, Redis, Celery, and HTTPS configuration. Docker Compose development uses the internal `db` and `redis` service names and disables HTTPS redirect, HSTS, and secure cookies; optional direct-host processes should temporarily override those container hostnames in their shell.

The project writes rotating system, activity, and security log files in `logs/`. Logging helpers do not add passwords, OTP values, JWTs, or credentials themselves, but callers must keep sensitive values out of log messages. Current OTP-related services log some phone numbers, so protect log access and retention as operational data. Do not expose internal exception details in API responses.

## Current limitations

- OTP delivery is only a Celery task placeholder; an SMS provider is not implemented.
- OTP values are stored as cache values rather than password hashes; Redis access must be tightly restricted.
- The verification lease reduces concurrency risk but does not make verification a fully atomic Redis operation.
- The repository has no documented automated security scanning, production
  health endpoint, managed object storage, or production deployment automation.

Review security-sensitive changes for permissions, authentication, input validation, secret handling, cache-failure behavior, logging, uploads, concurrency, and database integrity. Report suspected vulnerabilities privately to the repository maintainer; do not include exploit details or real secrets in public issues.
