````markdown
# Security

## Overview

This document describes the current security model of the Wine Shop API.

The project applies security controls across several layers:

- Django and Django REST Framework permissions
- JWT authentication
- request throttling
- Redis-backed authentication guards
- model and database validation
- secure password handling
- upload validation
- generic authentication errors
- environment-based configuration
- logging boundaries

Security-sensitive behavior should remain explicit, testable, and fail-safe.

---

## Security Principles

The project follows these principles:

1. Protect endpoints by default.
2. Expose only endpoints that explicitly declare public access.
3. Never store plain-text passwords.
4. Never expose OTP values or tokens in logs.
5. Avoid account enumeration.
6. Rate-limit authentication endpoints.
7. Track repeated authentication failures.
8. Treat authentication-cache failures as security failures.
9. Validate uploaded files by actual content.
10. Enforce critical data invariants at model and database levels.
11. Keep secrets outside source control.
12. Prefer generic client errors and detailed internal diagnostics.

---

## Default API Protection

Django REST Framework uses:

```python
IsAuthenticated
````

as the global default permission.

This means a newly added endpoint is protected unless it explicitly declares:

```python
permission_classes = (AllowAny,)
```

This is safer than making endpoints public by default.

Public endpoints currently include:

* signup
* login
* OTP request
* OTP verification
* password reset
* public product list
* public product detail

Protected endpoints include:

* profile completion
* profile update
* logout
* product creation
* product update
* product deletion
* product image upload
* product image deletion

Catalogue mutations require administrator or staff-level access.

---

## JWT Security

The API uses Simple JWT.

Supported security behavior includes:

* short-lived access tokens
* longer-lived refresh tokens
* refresh-token rotation
* refresh-token blacklisting
* logout blacklisting
* Bearer authentication

Example request header:

```http
Authorization: Bearer <access-token>
```

Token lifetimes are configured through environment variables:

```env
JWT_ACCESS_TOKEN_LIFETIME_MINUTES=20
JWT_REFRESH_TOKEN_LIFETIME_DAYS=30
```

Short access-token lifetimes reduce the impact of a stolen access token.

Refresh-token rotation reduces reuse risk.

After rotation, the previous refresh token is blacklisted.

Logout blacklists the submitted refresh token.

An already issued access token normally remains valid until its expiry.

---

## Password Security

Passwords are stored using Django's password hashing system.

When a password is provided, the project uses:

```python
user.set_password(password)
```

This stores a password hash rather than the original password.

When a user is created through OTP without a password, the project uses:

```python
user.set_unusable_password()
```

An unusable password prevents accidental password login for OTP-only accounts.

Plain-text passwords must never be:

* stored in the database
* written to logs
* returned in API responses
* placed in cache
* committed to source control

---

## User Identity Integrity

An active user must have at least one identity:

* username
* phone number

The project protects this rule through:

* serializer validation
* service validation
* custom user manager validation
* model validation
* database constraint

The custom manager runs model validation before saving.

Inactive legacy users may exist without an identity, but they must receive a valid identity before reactivation.

Username casing is preserved in storage.

Username authentication and conflict checks are case-insensitive.

This prevents multiple new accounts from being created using visually equivalent username casing.

---

## Authentication Error Privacy

Authentication errors must not disclose account state.

Username/password failures use a generic response regardless of whether:

* the username does not exist
* the password is wrong
* the account is inactive
* the account has an unusable password
* case-conflicting legacy records exist

OTP request responses also remain generic.

A client should not be able to determine whether a phone number belongs to an account by comparing normal API responses.

Internal logs may record additional security context, but client responses must remain generic.

---

## Request Throttling

Django REST Framework throttles authentication endpoints.

Configured throttle scopes include:

```text
anonymous requests
authenticated requests
OTP requests
OTP verification
signup
password login
```

Example environment configuration:

```env
AUTH_ANON_THROTTLE_RATE=100/day
AUTH_USER_THROTTLE_RATE=1000/day
OTP_REQUEST_THROTTLE_RATE=1/m
OTP_VERIFY_THROTTLE_RATE=10/m
SIGNUP_THROTTLE_RATE=5/hour
PASSWORD_LOGIN_THROTTLE_RATE=10/m
```

Throttling limits request frequency.

It is separate from failed-attempt tracking.

Both protections are required because they address different abuse patterns.

---

## Security Cache

Authentication security state is stored in a dedicated Redis cache alias.

This cache is separate from ordinary response caching.

It stores:

* OTP values
* OTP failed-attempt counters
* OTP lock states
* OTP verification leases
* password-login failed-attempt counters
* password-login lock states

The security cache is fail-closed.

If Redis cannot safely read or update security state, the API raises:

```text
503 Service Unavailable
```

This prevents an attacker from bypassing OTP or login protection during a cache outage.

The implementation uses a dedicated `security` cache alias without silent exception suppression.

---

## OTP Storage

OTP values are stored temporarily in Redis.

They are not stored permanently in PostgreSQL.

Each OTP is associated with:

* a purpose
* a normalized phone number

Conceptual key format:

```text
security:otp:<purpose>:<phone-number>:code
```

Supported purposes include:

```text
signup
login
password reset
```

Purpose separation prevents an OTP generated for one flow from being reused in another flow.

---

## OTP Generation

OTP codes are generated using Python's `secrets` module.

This is intended for cryptographic randomness.

OTP generation must not use predictable functions such as:

```python
random.randint(...)
```

OTP values must never be logged.

The OTP should only be sent to the intended delivery channel and stored temporarily in the security cache.

---

## OTP Expiry

OTP expiration is configurable:

```env
OTP_EXPIRY_SECONDS=120
```

After expiry:

* the OTP is no longer accepted
* verification returns the same generic error used for an invalid code
* clients cannot distinguish invalid from expired OTP values

Keeping the error generic reduces information leakage.

---

## OTP Failed-Attempt Protection

Invalid OTP submissions increment a failed-attempt counter.

Configuration:

```env
OTP_VERIFICATION_MAX_ATTEMPTS=5
OTP_VERIFICATION_LOCK_SECONDS=300
```

After the maximum number of failures:

* verification is temporarily locked
* further attempts return a throttle response
* the lock expires automatically

Successful verification clears:

* the OTP
* the failed-attempt counter
* the lock state

The current OTP guard stores these values in separate Redis keys.

---

## OTP Replay Prevention

A valid OTP is deleted after successful verification.

This prevents the same code from being accepted again.

The verification process uses a short Redis lease:

```text
security:otp:<purpose>:<phone>:lease
```

The lease reduces the chance of multiple concurrent requests verifying the same OTP simultaneously.

If another verification is already in progress, the request receives a temporary throttle response.

The current implementation uses cache `add()` to acquire this lease before reading and consuming the OTP.

---

## Constant-Time OTP Comparison

OTP values are compared using:

```python
secrets.compare_digest(...)
```

This reduces timing differences between matching and non-matching values.

Constant-time comparison is useful when checking secrets because ordinary equality comparisons may theoretically expose small timing variations.

---

## Password Login Guard

Repeated username/password failures are tracked in Redis.

The guard is scoped by:

* normalized username
* client IP address

Conceptual key:

```text
security:password-login:<username>:ip:<client-ip>
```

This isolation means:

* one IP cannot directly share lock state with another IP
* different usernames from the same IP have separate lock state
* successful login clears only the matching username/IP state

The implementation constructs the cache prefix from both case-folded username and client IP.

Configuration:

```env
PASSWORD_LOGIN_MAX_ATTEMPTS=5
PASSWORD_LOGIN_LOCK_SECONDS=300
```

---

## Login Lock Behavior

Before password authentication, the guard checks whether the username/IP pair is locked.

After an authentication failure:

1. the attempt counter is created if missing
2. the counter is incremented
3. the pair is locked when the threshold is reached

After successful login:

* the counter is removed
* the lock state is removed

Locks are temporary.

The application does not permanently disable the account.

This reduces brute-force risk without introducing permanent account lockout.

---

## Client IP Handling

Password-login protection depends partly on the client IP address.

In production, the reverse proxy must correctly set:

```http
X-Forwarded-For
X-Real-IP
X-Forwarded-Proto
```

The application must trust forwarded headers only from controlled proxies.

An unsafe proxy configuration can allow clients to spoof IP-related values and weaken IP-scoped protection.

---

## Redis Operational Security

Redis is a required security dependency.

Production Redis should:

* not be exposed publicly
* be bound to a private interface
* use ACLs or authentication
* use TLS across untrusted networks
* have enough memory to prevent unexpected eviction
* be monitored for availability
* restrict access to trusted application hosts

Authentication security keys should not be evicted during normal operation.

A Redis outage may temporarily disable authentication actions by returning `503`, which is intentional.

---

## Image Upload Security

Product, category, and brand images use shared validation.

Accepted formats:

```text
JPEG
PNG
WebP
```

The validator checks:

* declared MIME type
* actual image format
* MIME/content consistency
* file size
* image dimensions
* file corruption
* decompression-bomb warnings
* unsafe filenames
* file-pointer position

The current maximums are:

```text
5 MB
6000 × 6000 pixels
```

The image validator uses Pillow to inspect and verify the actual file content rather than trusting the file extension alone.

---

## MIME Validation

The client-provided MIME type is preserved before serializer processing.

The validator then compares it with the format detected by Pillow.

Examples:

```text
image/jpeg must contain JPEG data
image/png must contain PNG data
image/webp must contain WebP data
```

A file named `.jpg` that actually contains another format is rejected.

A valid image with an unsupported declared MIME type is also rejected.

---

## Corrupt Image Protection

The validator uses:

```python
Image.open(...)
image.verify()
```

It then reopens and loads the image.

This detects:

* malformed files
* truncated data
* non-image payloads
* some corrupted images

Validation errors return a generic upload error rather than exposing Pillow internals.

---

## Decompression-Bomb Protection

Pillow may raise warnings or errors for images whose decompressed size is unexpectedly large.

The validator converts decompression-bomb warnings into validation failures.

This reduces the risk of attackers uploading compressed files that consume excessive memory during decoding.

---

## Filename Sanitization

Uploaded filenames are sanitized before storage.

The validator:

1. removes directory components
2. extracts the stem
3. applies Django filename sanitization
4. removes leading dots
5. limits stem length
6. assigns a validated extension based on actual MIME type

This prevents unsafe names such as:

```text
../../malicious.jpg
.hidden-file.png
```

from being stored unchanged.

---

## File Pointer Reset

Image validation reads the uploaded file multiple times.

The validator resets the file pointer using:

```python
value.seek(0)
```

after verification and before returning the validated file.

Without this reset, later storage or thumbnail code could receive an exhausted file stream.

---

## Category Hierarchy Integrity

Category parent relationships are validated to prevent:

* self-parenting
* direct cycles
* indirect cycles

Example invalid hierarchy:

```text
A → B → C → A
```

The validation walks through ancestors while tracking visited IDs.

This avoids infinite recursion and protects catalogue hierarchy integrity.

---

## Database Constraints

Critical invariants are enforced at the database level when practical.

The active-user identity constraint ensures an active user has:

* a non-empty username
* or a non-empty phone number

Database constraints protect data integrity even when writes occur outside normal serializers or services.

Application-level validation should still run first to provide clearer errors.

---

## Environment and Secret Management

Secrets and deployment-specific values are loaded from environment variables.

The real `.env` file must not be committed.

`.env.example` may be committed because it contains placeholders and documented defaults.

Sensitive environment values include:

* `SECRET_KEY`
* database password
* Redis credentials
* external messaging credentials
* production hostnames
* future payment credentials

Before committing, verify:

```bash
git status
git diff --cached
```

Never add the real `.env` using force options.

---

## Django Production Security

Production should use:

```env
DEBUG=False
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

Recommended HSTS settings should be enabled only after HTTPS is confirmed:

```env
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
```

Production must also configure:

```env
ALLOWED_HOSTS=api.example.com
CORS_ALLOWED_ORIGINS=https://shop.example.com
CSRF_TRUSTED_ORIGINS=https://shop.example.com
```

Do not use unrestricted production host or origin settings.

---

## CORS

CORS defines which browser origins may call the API.

Production CORS settings should list only trusted frontend origins.

Avoid:

```text
*
```

unless the API is intentionally public and credential behavior is fully understood.

CORS is not an authentication system.

Server-side permissions must still protect private endpoints.

---

## CSRF

JWT-authenticated API requests using Authorization headers are generally not authenticated through Django session cookies.

However, Django admin and any session-based endpoints still rely on CSRF protection.

The CSRF middleware should remain enabled.

Trusted origins should be configured precisely.

---

## Logging Security

The project separates:

* system logs
* activity logs
* security logs

Logs must never include:

* passwords
* OTP values
* access tokens
* refresh tokens
* secret keys
* database passwords
* raw authorization headers

Security logs may record events such as:

* repeated failed login attempts
* OTP requests for unknown accounts
* permission failures
* suspicious upload failures

Client-facing messages should remain generic even when internal logs are more specific.

---

## Error Handling

Expected security failures should use appropriate responses:

```text
400 validation failure
401 authentication failure
403 permission denied
429 throttle or temporary lock
503 security cache unavailable
```

Unexpected exceptions should reach the standard DRF exception handler.

Internal exception details must not be returned to the client.

Broad exception handling should not convert server errors into misleading `400` responses.

---

## Dependency Security

Dependencies are pinned in `requirements.txt`.

Security-sensitive dependencies include:

* Django
* Django REST Framework
* Simple JWT
* Pillow
* psycopg
* django-redis
* Redis client
* Celery

Dependency versions should be updated deliberately and tested.

A dependency update should include:

1. changelog review
2. compatibility checks
3. full test run
4. Django system checks
5. migration checks
6. deployment validation

Avoid installing both source and binary variants of the same PostgreSQL driver without a documented reason.

---

## Security Testing

Tests should cover:

* anonymous access to protected endpoints
* non-admin catalogue mutation attempts
* username/password failure lockouts
* IP and username lock isolation
* successful login state reset
* valid OTP
* invalid OTP
* expired OTP
* reused OTP
* OTP lockout
* OTP namespace isolation
* Redis failure behavior
* identityless active user rejection
* invalid phone creation
* category cycles
* invalid image types
* MIME mismatch
* corrupt images
* oversized images
* excessive dimensions
* unsafe filenames

Run:

```bash
venv/bin/python -m pytest
venv/bin/python manage.py check
venv/bin/python manage.py check --deploy
venv/bin/python manage.py makemigrations --check --dry-run
```

---

## Security Review Checklist

Before merging authentication or upload changes:

```text
[ ] Public endpoints explicitly use AllowAny
[ ] Protected endpoints remain authenticated
[ ] Admin-only operations enforce staff permissions
[ ] Authentication errors remain generic
[ ] No secrets are logged
[ ] No plain-text passwords are stored
[ ] OTP values expire
[ ] OTP values cannot be reused
[ ] OTP purposes remain isolated
[ ] Failed attempts are limited
[ ] Redis failure behavior remains fail-closed
[ ] Uploads are validated by content
[ ] Database invariants remain enforced
[ ] Environment secrets are not committed
[ ] Relevant tests pass
```

---

## Current Limitations

The current security model does not yet include:

* multi-factor authentication combining password and OTP
* device or session management
* access-token revocation before expiry
* email verification
* audit-log storage outside local files
* malware scanning for uploaded media
* automated dependency scanning workflow
* dedicated secrets manager
* Web Application Firewall configuration
* security headers managed by a reverse proxy policy
* intrusion detection

These may be added later as separate, reviewed features.

---

## Reporting Security Issues

Security-sensitive reports should not include:

* real passwords
* active OTP values
* production tokens
* production database credentials
* private customer data

For a public repository, avoid publishing exploitable production details in a public issue.

Use a private reporting channel when the project is deployed publicly.
