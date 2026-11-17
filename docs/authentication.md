# Authentication

## Scope and availability

Users owns identity, profiles, password credentials, purpose-specific OTP
workflows, and Simple JWT sessions. This guide explains their lifecycle; the
[API reference](api.md#users) owns complete route/request/response tables.
[Security](security.md) covers broader trust boundaries and known limitations.

Username/password signup, login, and authenticated password change work without
SMS. The backend also implements OTP signup/login, initial password setup,
recovery, and profile-phone verification. These require operational SMS and
return generic 503 while disabled, unregistered, or misconfigured. No real SMS
adapter is registered in this repository; test adapters are not integrations.
`GET /api/v1/users/auth-capabilities/` returns `sms_available`, based on the
feature flag, registered provider, callable send method, and configuration
checks. This is configuration readiness, not proof of network/handset delivery.

Human-readable messages negotiate English or Persian through Django's language
cookie and then `Accept-Language`, falling back to English. Compatible `fa-IR`
selects Persian. JSON keys, codes, status values, URLs, and input contracts stay
unchanged. Clients should use HTTP status and field keys rather than matching
translated prose.

## Identity and password rules

An active account must have a username or phone. Username and email values are
trimmed, retain display casing, and have conditional case-insensitive database
uniqueness for nonblank values. Username signup/profile input accepts 5–150 ASCII
letters, digits, or underscores. Login trims and looks up usernames
case-insensitively; it does not require clients to lowercase them.

Phone values must match `09[0-9]{9}`: eleven ASCII digits beginning with `09`.
International formats and Unicode digits are rejected. Submit the canonical
value without whitespace; the request field has an eleven-character cap.
Verification accepts six ASCII digits in `otp`. Password fields preserve
whitespace rather than trimming it and have a 128-character API maximum.

Django hashes stored passwords using its configured hashers. All supported API
credential mutations use the shared Django policy:

- at least 12 characters;
- user-attribute similarity checks;
- common-password rejection;
- entirely numeric password rejection.

Signup validates against the proposed username. Change/setup validate against
the locked user. Recovery first applies account-independent validation, then
user-aware validation only after proving the OTP. Model `set_password()` alone
is not a substitute for these service/serializer checks. Test settings deliberately
use a faster hasher; they do not define deployment hashing.

OTP signup creates an active phone-only account with an unusable password.
Such an account cannot use password login or password recovery to bypass initial
setup. The superuser manager requires a password and staff/superuser flags.
An enabled account (`is_active`) and a completed customer profile are separate
concepts; onboarding does not activate or change credentials.

## Endpoint permission boundaries

Global DRF authentication is bearer JWT and the default permission is
`IsAuthenticated`. Users views override those defaults deliberately:

| View group | Permission/authentication boundary |
| --- | --- |
| Signup/login/reset OTP requests | Explicit `AllowAny`; no cookie issuance or Origin permission; normal JWT authentication remains enabled |
| Direct signup, password login, OTP signup/login verification, reset verification | Anonymous-capable `CookieAuthOriginPermission`; default JWT authenticator remains enabled |
| Refresh and logout | `CookieAuthOriginPermission`; no bearer authentication; operate on the refresh cookie |
| Current profile, profile onboarding/updates, profile-phone verification, Change Password, initial Set Password | `IsAuthenticated`; identity is the current active token user |
| Auth capabilities | `AllowAny` and no authentication; no Origin/cookie requirement |

An invalid bearer header can fail authentication even on a public view that
retains JWT authentication. Public does not mean every supplied credential is
ignored. Frontend protected routes are navigation guards; backend permissions
and owner-scoped queries remain authoritative.

`CookieAuthOriginPermission` requires an exact `Origin` equal to the request's
scheme/host or an entry in `CORS_ALLOWED_ORIGINS`. Missing or untrusted Origin
returns 403, including for command-line clients. OPTIONS is allowed; CORS
middleware handles configured browser preflight. This permission does not read
`CSRF_TRUSTED_ORIGINS`. CORS, Django CSRF protection, cookie SameSite policy, and
this explicit Origin check have different roles; see [Security](security.md).

## JWT lifecycle and cookie contract

### Token ownership and refresh

Defaults in `config/settings/base.py` are 20 minutes for access and 30 days for
refresh, configurable with `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` and
`JWT_REFRESH_TOKEN_LIFETIME_DAYS`. JWT signing uses the dedicated
`JWT_SIGNING_KEY`. Successful signup/login/OTP recovery returns
`tokens.access` in JSON; refresh returns top-level `access`.

The refresh token is never included in these JSON responses. It lives in a
persistent cookie with expiry/max-age aligned to its token expiry:

| Attribute | Tracked value |
| --- | --- |
| Name | `exon_refresh_token` |
| Path | `/api/v1/users/` |
| Domain | Unset: host-only |
| HttpOnly | True |
| SameSite | `Lax` |
| Secure | False in base/development; True in production |

Clients send access as `Authorization: Bearer <access-token>`. For cross-origin
browser authentication/refresh/logout, include credentials and use an allowed
Origin. HttpOnly prevents JavaScript from reading the cookie; it does not itself
prevent the browser from attaching it to requests. No secret belongs in a
browser-visible `VITE_*` value.

`POST /api/v1/users/token/refresh/` reads only the cookie, not a submitted JSON
refresh value. It locks the user, checks active/password state, rotates refresh,
and blacklists the superseded token. Its response updates the cookie; replay
of the old token is rejected. Missing/invalid/expired/blacklisted cookies return
401 and expire the scoped cookie. Sensitive auth views apply no-store/private
and compatible no-cache headers, including on their error responses.

### Password revocation and logout limits

Simple JWT's password-state claim binds tokens to the current stored password
hash. Successful change/setup/recovery locks the user and blacklists unexpired
outstanding refresh tokens. Subsequent authentication rejects access tokens
bound to the previous password state, and refresh rejects mismatched or missing
revocation claims. Refresh uses the same user-row lock as credential mutation
before minting a rotated session. This is password-state checking plus refresh
blacklisting, not a database blacklist lookup for every access token.

`POST /api/v1/users/logout/` blacklists the supplied valid refresh cookie and
expires it. Missing, invalid, expired, or previously blacklisted cookies still
produce idempotent 200. Logout ignores an expired bearer token because bearer
authentication is disabled on that view. It requires trusted Origin and remains
subject to its normal throttling. Logout does **not** revoke every device or
already-issued access token; those can remain usable until expiry or another
revocation condition such as a password change.

## Password workflows

### Username/password signup and login

`POST /api/v1/users/signup/` creates an active username/password account and
returns 201 with `user.username`, `tokens.access`, and the refresh cookie. It
does not require a phone or complete profile. Duplicate case variants and
concurrent uniqueness conflicts return generic 400 `non_field_errors`.

`POST /api/v1/users/login/userpass/` returns 200 with `message`, `tokens.access`,
and the cookie. Unknown, ambiguous, inactive, unusable-password, and incorrect
password cases share generic 401 credentials errors. Missing/ambiguous/OTP-only
identities perform dummy password work to reduce timing differences. Dedicated
rate and failed-attempt guards are described below.

### Authenticated Change Password

Send `current_password` and `password` to
`POST /api/v1/users/password/change/` with bearer authentication. The service
locks/reloads the user, requires an active account with a usable password,
checks the current password, and validates/saves the new one. Invalid current
credentials, OTP-only accounts, or policy failures return 400.

Successful change revokes prior refresh sessions and invalidates old
password-bound JWTs. The 200 response contains `message`, expires the refresh
cookie, and issues no new token. Sign in again. SMS is not required.

### Initial Set Password for OTP-only accounts

Both setup operations require an authenticated active user with:

- no usable password;
- an existing account phone;
- a nonblank normalized username;
- operational SMS.

Save a username with `PATCH /api/v1/users/profile/update/` first if missing.
The prerequisite makes username/password sign-in usable after setup. Supported
OTP signup/profile-phone flows establish the phone through verification; the
underlying model stores a phone field, not a separate verification timestamp.
Privileged/direct data writes must not be mistaken for an OTP verification event.

1. `POST /api/v1/users/password/set/send-otp/` has no input fields (send `{}`).
   It derives the phone from the account and issues a fresh account-bound code.
   A 200 contains `message` and `expires_in`. **Sending this code does not change
   the password, revoke tokens, or expire the refresh cookie.**
2. `POST /api/v1/users/password/set/verify/` accepts `otp` and `password`.
   Verification locks the challenge and user, rechecks eligibility and unchanged
   phone, validates the password, saves its hash, revokes refresh sessions, and
   redeems the challenge in one database transaction.
3. Only successful verification returns 200 with `message`, expires the refresh
   cookie, and invalidates old password-bound JWTs. It issues no replacement
   token; sign in again. An existing usable password or missing username blocks
   setup with 400. Invalid OTP or policy errors do not complete setup.

### Forgotten Password / Recovery

With operational SMS, `POST /api/v1/users/password-reset/send-otp/` accepts
`phone_number` and returns the same `message`/`expires_in` for eligible, unknown,
inactive, and OTP-only accounts. Only active accounts with usable passwords
receive a recovery code. Request success changes no password/session and is not
a delivery receipt.

`POST /api/v1/users/password-reset/verify-and-reset/` accepts `phone_number`,
`otp`, and `password`, with trusted Origin. It performs account-independent
password checks before OTP verification, then locks/revalidates the matching
active password user and applies the full user-aware policy. Policy/database
failure rolls back redemption so a still-valid code can be retried.

Success saves the password, revokes previous sessions, and atomically issues a
replacement session with redemption. The 200 response returns `message`,
`tokens.access`, and a new refresh cookie. Recovery does not ask for the old
password; it cannot establish the initial password of an OTP-only account.

## OTP scopes and lifecycle

### Scope and business effects

A scope combines purpose and canonical phone. Authenticated purposes also bind
the current account; codes are not interchangeable across these scopes.

| Purpose | Phone source | Successful verification |
| --- | --- | --- |
| `signup` | Request | Creates an active phone-only account and issues tokens (201) |
| `login` | Request | Requires an active matching account and issues tokens (200) |
| `password-reset` | Request | Changes an existing password and issues replacement tokens (200) |
| `password-set:<user-id>` | Account | Sets initial password and invalidates prior sessions; no new tokens (200) |
| `profile-phone:<user-id>` | Candidate request phone | Attaches the previously absent phone; profile in `data`, no new tokens (200) |

Signup requests for already-owned phones and login requests for unknown phones
retain generic success responses; verification enforces eligibility. Profile-
phone requests do the same when a phone is already attached or belongs to
another account. Verification cannot replace an existing phone or claim another
account's phone. Supported phone-establishment flows are OTP signup and the
authenticated profile-phone pair.

### Issuance, redemption, and rollback

[`OTPVerificationGuard`](../apps/lib/security_cache.py) coordinates PostgreSQL
and the `security` cache:

1. Issue/resend creates/finds and locks an `OTPChallenge` identified by an
   HMAC-derived scope. It rotates a UUID generation, sets database expiry,
   clears redemption, and writes the generation/code pair to Redis with a TTL.
   Generated codes are six ASCII digits; an immediate resend avoids reusing
   the active cached code. Resend does not clear attempts or lockouts.
2. Verification checks the lockout and acquires a token-owned five-second Redis
   admission lease. It then locks the database challenge, rechecks lockout,
   expiry/redemption, cached generation, and the code using constant-time
   comparison. Busy admission is 429. The lease reduces overlapping work;
   database locking/redemption is the committed replay-prevention authority.
3. The success callback executes in the challenge transaction. Relevant callbacks
   lock/revalidate the user; account changes, issued/revoked token records,
   and redemption commit together. Failed callbacks or database commits roll
   those writes back; a still-valid unchanged code can be retried.
4. After commit, cleanup locks/rechecks the generation and redemption before
   deleting code/attempt/lock keys. It cannot delete a newer resend. Failed
   cleanup does not undo committed redemption; leftover code cannot authorize
   a second success for that generation. Lease release uses atomic ownership
   comparison in Redis.

PostgreSQL stores scope/generation/expiry/redemption, not the OTP value or phone
field in the challenge row. Redis codes are not password hashes. There is **no
distributed transaction**: Redis writes can outlive database rollback, and
Redis state can disappear independently. Missing or mismatched state fails
closed and requires reissuance; temporary attempt/lock history is not durable
PostgreSQL state. Failed OTP guesses update Redis even though database work rolls
back. Tests with LocMem cannot prove real Redis atomicity; see [Testing](testing.md).

### SMS delivery boundary

After issuance commits, Users queues the phone/code to Celery. The task renders
a fixed Persian message through the provider-neutral SMS transport. Neither
HTTP success nor provider acceptance proves handset delivery. Task publication
can fail after the challenge has committed; Users OTP has no durable Notification
outbox row or delivery/manual-review record.

The task retries `SmsTransportError` up to three times with backoff/jitter;
ambiguous results retry only for adapters declaring idempotent sending.
Configuration/protocol failures, rejection, and non-idempotent ambiguity do not
become successful delivery. Redacted argument representations and fixed log
events minimize exposure, but the actual broker payload contains the phone and
code; protect broker/AOF access. Cache expiry still bounds code validity.

## Throttling and trusted client IP

Custom authentication throttles and login/OTP guards use `caches["security"]`.
Cache exceptions return 503 rather than silently allowing unprotected work.
This differs from the ordinary `default` catalogue cache and global DRF
anonymous/user throttles.

| Control | Tracked default and key |
| --- | --- |
| Direct signup | `SIGNUP_THROTTLE_RATE=5/hour`, AUTH client IP |
| Password login / authenticated password change rate | `PASSWORD_LOGIN_THROTTLE_RATE=10/m`, AUTH client IP |
| Failed password-login guard | `PASSWORD_LOGIN_MAX_ATTEMPTS=5`, `PASSWORD_LOGIN_LOCK_SECONDS=300`; casefolded username + AUTH IP; cleared on successful login |
| OTP request | `OTP_REQUEST_THROTTLE_RATE=1/m`, normalized phone or setup account; plus `OTP_REQUEST_IP_THROTTLE_RATE=10/m` |
| OTP verification rate | `OTP_VERIFY_THROTTLE_RATE=10/m`, phone or setup account; plus `OTP_VERIFY_IP_THROTTLE_RATE` (defaults to the verification rate) |
| OTP expiry/failed-guess lock | `OTP_EXPIRY_SECONDS=120`, `OTP_VERIFICATION_MAX_ATTEMPTS=5`, `OTP_VERIFICATION_LOCK_SECONDS=300`, per purpose/account/phone scope |
| Refresh | `TOKEN_REFRESH_THROTTLE_RATE=30/m`, AUTH client IP; independent of the global anonymous bucket |

Phone rate keys share their request/verification scope across applicable flows;
challenge purposes remain separate. Malformed phone input falls back to an
IP-based rate key. The failed guess reaching the limit returns 400 and establishes
a lock; subsequent locked verification returns 429. Rate histories use DRF's
get/set accounting and are not an exact atomic concurrency quota. Redis counters
and compare/delete leases provide separate primitives.

`AUTH_TRUST_PROXY_HEADERS` governs the project's AUTH client-IP extraction used
by these custom throttles and the password-login guard. It defaults to false:
use `REMOTE_ADDR` and ignore forwarded headers. Behind a reverse proxy this may
attribute clients to the proxy until reviewed trust is configured. When enabled,
only a connecting peer in explicit valid `AUTH_TRUSTED_PROXY_CIDRS` may supply a
bounded, valid `X-Forwarded-For` chain. The extractor walks trusted hops from the
right; malformed chains fall back to the peer. No production CIDR is assumed.

This setting does **not** control ordinary DRF anonymous/user/catalogue throttle
identity logic. Those use DRF's own `get_ident()`/`NUM_PROXIES` behavior; production
sets `NUM_PROXIES` via `DRF_NUM_PROXIES`. Proxy counts alone are not CIDR trust.
See [Security](security.md) for threat boundaries and [Deployment](deployment.md)
for operational configuration.

## Profile ownership and sessions

`GET /api/v1/users/profile/` resolves only the authenticated user and returns
`data` with safe identity/customer fields, owned addresses, `has_usable_password`,
and `sms_available`. No user ID is accepted. The GET orders addresses by creation
and ID. Password hashes, token values, and privilege/group fields are excluded.

`is_profile_complete` is derived from username, stored phone, email, first/last
names, and at least one address. It does not independently query verification
history. Supported API phone-establishment workflows require OTP, but an Admin
or direct database write is a separate trust boundary. Incomplete users can use
ordinary authenticated APIs such as Cart; Payment initialization alone adds the
reusable complete-active-profile permission.

`POST /api/v1/users/profile/complete/` fills username/email/names and creates the
first address, requiring an existing phone and no address. Repeat edits use
`PATCH /api/v1/users/profile/update/`. An address update includes its explicit
owned UUID `id`; a foreign/missing address returns 400, not a writable foreign
resource. Without an ID the API only creates the first address. User/address
writes lock the owner and apply together. They cannot change activation or
privileges through their input serializers.

Both profile serializers/services reject `password` and `current_password`;
use dedicated credential endpoints. Ordinary profile edits and profile-phone
verification preserve password state and existing sessions and issue no new JWT.
Onboarding also issues no JWT. Sending any OTP alone does not change credentials
or establish a session.

## Frontend session and feature availability

[`AuthContext`](../frontend/src/context/AuthContext.jsx) centralizes signup,
login, recovery, logout, and restoration. Access tokens live only in JavaScript
memory; refresh cookies are backend/browser-owned. Tokens are not persisted in
localStorage or sessionStorage; initialization removes a legacy refresh key.

Startup attempts refresh before exposing authenticated providers. A refresh 401
clears memory and enters `anonymous`. Network errors, 429, other non-401 failures,
or malformed successful refresh responses enter retryable `restoration_error`;
they are not treated as proof that the cookie is invalid. This does not establish
that a valid session exists. Protected 401 requests share an in-flight refresh
and retry once after a valid access token. Web Locks serialize cookie operations
across tabs when supported; the fallback does not provide that cross-tab lock.

The `/account` page keeps profile/drafts in React memory and uses profile GET and
PATCH; Cart mounts its owner-bound state only while authenticated. Successful
change/setup clears the memory token and navigates to `/login` with a sign-in
prompt. Recovery establishes the returned session and navigates to `/account`.
Logout clears frontend auth state after server success; failed logout is shown
as retryable rather than claiming completion.

`/forgot-password` is capability-gated and shows an unavailable message when SMS
is unavailable. Initial setup additionally uses profile username, phone,
`has_usable_password`, and `sms_available`; a missing username prompts a profile
save first. The visible SMS signup/login controls remain disabled even when
SMS capability becomes available. Account-phone verification is not implemented
in the storefront. These are separate UI boundaries from implemented backend
OTP endpoints; see [Frontend](../frontend/README.md).
