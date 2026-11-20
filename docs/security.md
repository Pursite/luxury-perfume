# Security

This document describes implemented controls, trust boundaries, and known
limitations. It is not a security certification. [Architecture](architecture.md)
explains domain design; [Authentication](authentication.md) and [API](api.md)
own detailed flows/contracts; [Deployment](deployment.md) owns operational setup.

## Authentication, permissions, and ownership

[`config/settings/base.py`](../config/settings/base.py) defaults DRF to Simple
JWT bearer authentication and `IsAuthenticated`. Views can replace permissions,
authentication, and throttles; authentication routes do not all use `AllowAny`.

| Entry point | Implemented boundary |
| --- | --- |
| Username/password signup/login, OTP signup/login verification, password-reset verification | `CookieAuthOriginPermission`; reachable anonymously but requires a trusted Origin for the token/cookie operation |
| Refresh and logout | Cookie-based operations with `CookieAuthOriginPermission`; no valid access token required |
| Signup/login/reset OTP requests | Explicit `AllowAny` plus phone/IP security throttles and SMS availability checks |
| Auth capabilities | Explicit `AllowAny`, authentication disabled; exposes only SMS capability |
| Profile reads/updates/onboarding, phone verification, password change/setup | `IsAuthenticated`; operate on the requesting account |
| Product reads | Explicit public access; active catalogue for anonymous/non-staff, with inactive detail access for staff |
| Product/image mutations | Authenticated `is_staff` through `IsAdmin` plus the operation's Django model permission |
| Cart and Order reads | Authenticated owner-scoped state; foreign identifiers do not confer access |
| Payment initialization/detail | Authenticated, owner-bound; initialization additionally requires complete active profile and dedicated throttle |
| Payment callback | Explicit public access with authentication disabled, dedicated throttle, registered provider parsing, and server-to-server verification |

A public permission does not disable request validation or throttling. Where
views retain JWT authentication, supplied invalid bearer credentials can fail
even if the permission itself does not require a login. The plain Django health
views are outside DRF authentication/throttling and expose only bounded status.

Profile and Cart ownership comes from `request.user`, not client-supplied user
IDs. Order and Payment selectors filter by owner before UUID lookup. UUIDs and
slugs are identifiers, not authorization. Products are a staff-managed shared
catalogue, not customer-owned resources. React protected routes control
navigation; backend permissions/querysets enforce access.

### Django Admin boundaries

`is_staff` permits Admin-site login, while model permissions still govern
access. Delegated non-superuser staff cannot manage privileged users/addresses,
assign groups/direct permissions, or administer permission groups. User/address
Admin querysets and object permissions enforce that boundary; mutation services
lock current owners and recheck protected relationships.

Cart Admin is read-only. Cart, Order, Payment/Refund, and SMS Admin querysets
exclude privileged owners from delegated staff access. Backoffice applies the
same ownership boundary to details and aggregates and checks the relevant
model permission before reading data. Order shipping and delivery require
`orders.change_order`, recheck the owner under lock for delegated staff, and
write an Admin audit record in the transition transaction.

Financial reconciliation, manual Refund actions, and SMS manual-review retries
are superuser-only. SMS rearming and confirmed external Refund completion write
Admin audit records. SMS rearming requires explicit confirmation and a usable
provider. Deliveries that may have reached the provider also require safe
provider idempotency. Financial fields remain read-only. [Backoffice roles](backoffice.md#staff-roles)

## Passwords and JWT sessions

### Password policy and separate credential workflows

Passwords use Django's `set_password`/`check_password` APIs and configured
hashers, not plaintext persistence. Production inherits Django's default
hashers; the fast MD5 hasher is confined to test settings. The configured Django
validators require at least 12 characters and check user-attribute similarity,
common passwords, and entirely numeric passwords. API password fields cap
input at 128 characters and preserve password whitespace.

[`password_policy.py`](../apps/users/password_policy.py) applies those validators
in supported signup/change/setup/reset workflows. Model `save()` and arbitrary
ORM writes do not automatically invoke password validation.

| Workflow | Security property |
| --- | --- |
| Direct signup | Validates username/password against a candidate user; identity constraints protect concurrent conflicts |
| Authenticated Change Password | Locks/reloads active user, requires a usable password and correct current password, validates the new password |
| Initial Set Password | Requires active OTP-only account, nonblank existing username, account phone, operational SMS, and fresh `password-set:<user-id>` OTP; locked callback rechecks eligibility/phone |
| Forgot Password/recovery | Requires operational SMS and an eligible active account with a usable password/registered phone; valid OTP precedes user-aware password validation and mutation |
| Profile writes | Serializers and profile services reject `password`/`current_password`; credential mutation uses separate endpoints |

Username login is case-insensitive. Absent, ambiguous, inactive,
unusable-password, and incorrect-password outcomes share a generic failure.
Absent/ambiguous/unusable paths perform dummy password-hash work to reduce
practical timing enumeration; this is not a constant-time guarantee for the
whole HTTP request. OTP request responses for unknown/ineligible accounts are
also generic where implemented.

### Token storage, rotation, and revocation

Simple JWT uses HS256 with a dedicated `JWT_SIGNING_KEY`. Defaults are 20-minute
access tokens and 30-day refresh tokens, configurable through settings.
Browser responses return access tokens in JSON and place refresh tokens only in
the persistent `exon_refresh_token` cookie: HttpOnly, host-only, path
`/api/v1/users/`, SameSite Lax, and Secure in production.

The React client keeps access only in JavaScript memory and writes neither token
to local/session storage. Its legacy storage cleanup is not a token store.
Login/signup return targets pass through the internal-path check before navigation.
HttpOnly prevents JavaScript reading the refresh cookie; it does not make
browser-executed script harmless or replace XSS prevention.

[`apps/users/jwt.py`](../apps/users/jwt.py) enables rotation and blacklist-after-
rotation. Refresh reads the cookie rather than a JSON refresh field, locks the
user, validates active/password state, and delegates rotation/blacklisting to
Simple JWT. Tokens include its password-hash revocation claim. Configured JWT
authentication rejects access tokens whose claim no longer matches the stored
password state; the custom refresh serializer enforces the same check.

Authenticated password change/setup and OTP recovery revoke all unexpired
outstanding refresh tokens while changing password state in a transaction.
Admin password changes use the revoking service; Admin deactivation blacklists
outstanding refresh sessions, and inactive-user checks reject access.
Authenticated change/setup expires the refresh cookie and requires sign-in
again. Recovery issues a replacement session after revoking old sessions.

Logout blacklists the supplied valid refresh token and expires its cookie;
missing/invalid/expired/already-blacklisted values are idempotent. It does not
blacklist access tokens or revoke every device session. A copied access token
can remain usable until expiry, password-state change, or account deactivation.
Sensitive authentication responses use no-store/no-cache headers; ordinary
profile/Cart responses do not inherit that authentication-response mixin.

### Origin, CORS, and cookies

[`CookieAuthOriginPermission`](../apps/users/permissions.py) accepts an exact
Origin equal to the API's scheme/host or an entry in `CORS_ALLOWED_ORIGINS`.
Missing/untrusted Origin is rejected for the protected operation; OPTIONS is
allowed for metadata/preflight. This applies even without a logged-in user on
token-issuing routes. It is not the same as unconditional public access.

DRF's JWT authentication does not supply SessionAuthentication's automatic CSRF
checks. Explicit Origin enforcement protects the implemented cookie/token
operations; credentialed CORS and SameSite Lax provide complementary browser
controls. `CSRF_TRUSTED_ORIGINS` is separately configured for Django CSRF policy;
it is not the allowlist consulted by this permission. Bearer-authenticated
account endpoints use authentication and ownership rather than this cookie-Origin
permission. CORS is a browser policy, not authorization for arbitrary clients.

Production settings enable HTTPS/cookie controls from explicit environment
settings and force Secure refresh cookies. The production template assigns
`shop.exonplus.ir` to Django and `https://www.exonplus.ir` to the storefront.
Host validation, allowed origins, forwarded-protocol trust, and TLS termination
must agree with the actual proxy layout. Do not disable validation or use
wildcards to resolve configuration problems.

## OTP protection and cross-store limits

Phone input is trimmed and must match ASCII `09[0-9]{9}`; OTP input is six ASCII
digits. Formatting variants and alternate digit sets are rejected. SMS-dependent
services check `sms_available()` and return 503 when SMS is disabled, its provider
is unregistered, or configuration is invalid. No real SMS adapter is registered
in this repository; these are implemented gated flows, not live SMS service.

### Purpose, generation, and durable redemption

[`OTPVerificationGuard`](../apps/lib/security_cache.py) uses distinct purposes:

| Purpose | Scope binding |
| --- | --- |
| `signup` | Phone |
| `login` | Phone |
| `password-reset` | Phone |
| `password-set:<user-id>` | Authenticated account and its phone |
| `profile-phone:<user-id>` | Authenticated account and candidate phone |

The guard derives an HMAC scope from the purpose/phone prefix. PostgreSQL
`OTPChallenge`, added by
[`users.0002_otpchallenge`](../apps/users/migrations/0002_otpchallenge.py), stores
scope/generation/expiry/redemption, not raw code or a recipient field. Redis
stores the matching generation and code plus temporary controls.

Issuance/resend locks the challenge and rotates its generation and code. Existing
failed-attempt counters and lockouts are retained rather than reset on resend.
Defaults are 120-second code expiry, five failed verification attempts, and a
300-second verification lock; settings control those values. Code TTL and durable
expiry are both checked. Attempts/locks are temporary Redis state, not permanent
account disablement.

Verification uses `compare_digest`, a short token-owned Redis admission lease,
and a PostgreSQL row lock. Redis release compares ownership atomically; the
LocMem fallback is for isolated tests. Under the database lock, verification
rechecks redemption, expiry, generation, and code before invoking the domain
callback. Callback writes and redemption commit in the same transaction.
Relevant callbacks lock/revalidate the user; initial signup relies on identity
uniqueness for creation.

The durable lock/redemption prevents a second committed success for the same
generation, including after the Redis lease expires. A failed callback or failed
commit rolls back both domain writes and redemption, permitting retry while
valid. Post-commit cleanup rechecks generation/redemption under lock before
removing code/attempt/lock state. Its failure cannot reopen committed redemption,
and old cleanup cannot erase a newer generation. Real-service tests cover these
specific cases; they do not establish universal race freedom.

### Failure and confidentiality boundaries

There is no PostgreSQL/Redis distributed transaction. Redis issuance writes can
outlive a database rollback; cache loss or mismatched generations fail closed
and require reissuance. Redis loss also loses temporary attempts/lockouts;
durable redemption protects already committed generations but does not recreate
all rate-limit history. Changing Django `SECRET_KEY` changes derived OTP scopes;
rotating `JWT_SIGNING_KEY` affects token verification. Both require an operational
transition plan.

OTP values in Redis are usable codes, not password hashes. The phone/code also
travel in the Users Celery task payload even though argument representations are
redacted. Redis broker data and AOF copies therefore need restricted access and
retention. Deleted/expired values can remain in historical AOF commands until
rewrite. Logical databases are not security principals.

Users OTP delivery retries known transport failures with bounded backoff/jitter;
ambiguous results are retried only for adapters declaring idempotent send.
Task publication and provider acceptance are separate from challenge issuance.
There is no durable Users OTP outbox/manual-review record and no guarantee that
an issued code was delivered. The React UI keeps SMS sign-in/signup disabled;
initial setup and recovery additionally depend on reported SMS capability.

## Throttles and security-cache failure policy

[`apps/lib/throttle.py`](../apps/lib/throttle.py) distinguishes ordinary DRF
throttles from custom security throttles:

| Mechanism | Cache/key policy |
| --- | --- |
| Global `AnonRateThrottle` / `UserRateThrottle` | DRF `default` cache and standard DRF identity logic |
| Catalogue read throttle | `default`, separate `catalogue` scope; DRF user/anonymous identity logic |
| Signup, password-login request, token-refresh throttles | `security`, custom AUTH trusted-client-IP extraction |
| OTP request/verification | `security`, normalized phone plus independent AUTH client-IP buckets; invalid phone uses an IP fallback |
| Initial password setup | `security`, account-bound `password-set:<user-id>` bucket plus independent AUTH IP bucket |
| Password-login attempt guard | `security`, case-folded username plus AUTH client IP; failed-attempt counter and temporary lock |
| Payment initialization | `security`, authenticated user bucket |
| Payment callback | `security`, PAYMENT trusted-client-IP extraction |

The `security` alias does not ignore backend failures. The guard/throttle
wrappers map protection failures to 503 rather than allowing an unprotected
request. Exceeded limits/active lockouts return 429. Ordinary catalogue caching
and its throttles use a performance cache configured to ignore exceptions;
continued catalogue access does not prove security-cache availability.

The shipped OTP request limits are one per phone/account per minute and ten
per IP per minute. Other request/verification rates, code expiry, attempts, and
lock durations are configured separately. Successful password login clears its
failed-attempt guard; it does not remove all request throttle history.

Custom fail-closed wrappers do not make DRF's list-based throttle accounting an
exact atomic quota under concurrent requests. Distinguish those histories from
Redis atomic increment/lease operations and durable OTP redemption. Throttles
are application abuse controls, not a network-level denial-of-service defense.

## Trusted proxy and client-IP boundary

[`apps/lib/client_ip.py`](../apps/lib/client_ip.py) starts with parsed
`REMOTE_ADDR`. AUTH policy uses `AUTH_TRUST_PROXY_HEADERS` and
`AUTH_TRUSTED_PROXY_CIDRS`; PAYMENT policy uses its corresponding
`PAYMENT_TRUST_PROXY_HEADERS` and `PAYMENT_TRUSTED_PROXY_CIDRS`.

With trust disabled, forwarded headers are ignored. With trust enabled, only an
explicitly trusted connecting peer can supply `X-Forwarded-For`. The bounded,
validated chain is walked from right to left through trusted hops to the first
untrusted address. Malformed/oversized chains or unusable trust configuration
fall back to the peer; an invalid peer returns no PAYMENT address and AUTH uses
an `unknown` bucket. Payment initialization rejects a missing/invalid canonical
initiator address before checkout, reservation, or provider side effects.

Authentication proxy trust defaults to disabled, including in the production
template. This resists forged forwarding headers but can group real clients
under the proxy's peer IP until the actual connecting CIDRs are configured.
`users.E001` rejects enabled AUTH trust without valid explicit networks.
Enabled Payments checks require explicit valid PAYMENT proxy trust as well.
Do not guess Docker gateway addresses or trust broad private networks by default.

These policies do **not** replace standard DRF IP logic everywhere. Production
sets `NUM_PROXIES` from `DRF_NUM_PROXIES` (default 1) for ordinary DRF throttles.
That is a hop-count rule, not a trusted-CIDR check. Catalogue/global throttles
therefore depend on the reverse proxy sanitizing forwarding headers and keeping
the Django upstream inaccessible to untrusted direct callers.

`SECURE_PROXY_SSL_HEADER` separately controls trust in forwarded HTTPS scheme;
it does not identify client IPs. The host-managed proxy must overwrite applicable
forwarding headers and be the only reachable upstream peer. See
[Deployment](deployment.md) for configuration procedures.

## Domain security and data integrity

### Accounts and profiles

Database constraints require an active account to have username or phone,
case-insensitive uniqueness for nonblank usernames/emails, and unique phones.
Profile completion is derived and is not activation. Incomplete accounts retain
ordinary authenticated access; `IsProfileComplete` is opt-in for Payment
initialization. Phone attachment is user-bound, locked, and protected by phone
uniqueness. Profile output omits password hashes and privilege/group fields;
owned address updates require an explicit matching ID.

### Catalogue, caching, and uploads

Product writes require staff at the API boundary and validated fields. Product
slugs are lowercase/immutable through supported write paths; the response UUID
is not a product URL. Shared response caches contain the same public/non-staff
representation; staff bypass them to avoid mixing inactive-detail visibility.
Cart and customer-specific data are not placed in catalogue response keys.

[`apps/lib/image_validation.py`](../apps/lib/image_validation.py) restricts
supported upload paths to JPEG/PNG/WebP, at most 5 MiB and 6000 pixels per
dimension. It verifies declared MIME against decoded format, fully loads content,
rejects corruption/decompression-bomb warnings, and sanitizes filenames.
Services assign collision-resistant original names; API/Admin lifecycle paths
coordinate rollback cleanup, primary-image changes, and deferred thumbnails.

Conditional primary-image uniqueness and note-layer constraints protect durable
metadata. Storage itself is not transactional; cleanup can fail or leave orphaned
files, and validation is not an antivirus/content-moderation service. Product
price positivity and several format/cycle rules are application validation,
not universal database checks. Arbitrary ORM/bulk writes must not be assumed
to preserve every supported-path invariant. Uploaded media is publicly served
by the documented layout; it is not a private customer-document store.

### Cart, Orders, Payments, and Notifications

| Property | Mechanism and boundary |
| --- | --- |
| Cart ownership/lost-update protection | Owner-derived selector/services; user → Cart → CartItem locking, uniqueness and positive quantities; no Product stock reservation |
| Checkout authority | Locked owned address and current Products, server-calculated snapshots, stock decrement/reservations and Cart capture in one transaction |
| Historical money | Exact server-owned shipping snapshot; database total/line equations; Payment amount derives only from locked `Order.total` |
| Reservation consistency | Orders owns consume/release/expiry; strict database deadline, ordered Product locks, idempotent lifecycle checks; Cart availability is not checkout authorization |
| Financial evidence | Callback data is only a hint; registered adapter parsing and server-to-server verification precede accepted capture; amount/currency/identity checks and Orders transitions govern application |
| Refund obligation | One full captured-amount obligation per Payment, stable UUID references, operation claims and provider identity uniqueness; real provider idempotency remains an adapter requirement |
| SMS obligation/delivery | Enabled Order transitions insert unique outbox rows, commit before enqueue, claim before provider I/O and token-check finalization; uncertainty may require manual review |

Payment initialization strictly rejects client amounts, currency, provider,
merchant identity, callback/return URLs, and shipping. Provider redirect URLs
must be HTTPS with an exact configured allowed hostname and no embedded
credentials. Owner Payment output omits provider session/transaction/receipt,
IP/user-agent and diagnostic evidence. Payment callbacks are not browser payment
proof, and callback response success alone is not proof of capture.

When enabled, [Payment system checks](../apps/payments/checks.py) require a
registered adapter's methods, HTTPS public/result URLs, allowed redirect hosts,
`IRT` currency, explicit valid proxy trust, and positive timeout/retention values.
SMS checks require provider configuration and positive timing/retry settings,
including a lease longer than the provider network budget. Passing configuration
checks does not prove successful provider I/O.

Commercial `PROTECT` relationships retain user/Product history; supported delete
paths map commercial conflicts to domain errors. Late/duplicate/mismatched
captures create Refund obligations, not revived Orders. A Payment in manual
review blocks another open attempt and requires explicit rearming for automated
reconciliation. This is not an exactly-once guarantee for external providers.

Notifications uses fixed server-controlled message templates rather than
client-supplied SMS. Owner alerts go only to active superusers with valid account
phones. Non-idempotent ambiguous delivery/stale claims require manual review;
`SENT` is provider acceptance, not handset receipt. SMS-disabled Order events
create no new outbox rows; re-enabling SMS does not backfill them.

## Logging, secrets, and transport

### Deliberate data minimization

[`JsonFormatter`](../apps/lib/logging.py) emits a small allowlisted JSON shape;
`AppLogger` supplies event/category/context fields. Common sensitive assignments,
JWT patterns, phones, and emails are redacted. Django log records handled by the
configured context filter use generic events. Structured exceptions include
exception type rather than exception text/traceback. Financial/notification audit
helpers use fixed event sets and bounded correlation fields, omitting transport
payloads, raw recipient data, and provider identifiers from those events.

`RequestIDMiddleware` generates the response/request correlation ID server-side
rather than trusting a client-supplied ID. Tasks using `CorrelatedTask` bind their
task ID during execution. The Users OTP task redacts argument representations
and returns bounded results; actual phone/code payloads remain in the broker.

These controls apply to the configured paths, not every possible logger,
third-party message, worker error, or future caller. Pattern redaction cannot
recognize arbitrary secret text. Callers must not log request bodies, headers,
query strings, passwords, codes, tokens, credentials, rendered SMS, or sensitive
internal errors. There is also a known formatter limitation: UUID-valued
`user_id` is passed unchanged to JSON encoding and can raise `TypeError`; do not
assume all user-linked events are successfully emitted until separately fixed.

Activity logs go to stdout; security/system/Django errors go to stderr. Gunicorn
has its own bounded access format excluding query strings and common client
metadata. Production Docker log rotation limits local storage, not archival
retention or external audit collection.

### Configuration and retained data

Runtime `.env` is private and ignored; tracked templates contain examples only.
Production needs distinct random Django and JWT signing keys; use at least 32
random bytes for the JWT key. Do not put secrets in source, logs, image build
arguments, release manifests, or browser-visible `VITE_*` values. Filesystem
permissions and host/registry/CI credentials remain operational responsibilities.

Payment IP/user-agent evidence is retained in the database and scrubbed by the
scheduled task after the configured period (default 180 days). SMS terminal
recipient snapshots have a separate retention period, also default 180 days;
the scrub task is gated by SMS enablement. Retention work does not imply all
historical commercial data is erased or all backups/AOF copies are scrubbed.

Django production disables DEBUG and configures HTTPS redirect, HSTS, secure
cookies, content-type and frame protections. Actual HTTPS depends on the
host-managed TLS proxy and correct forwarded-scheme policy. PostgreSQL/Redis
have no host-port mappings in the normal development/production Compose merges;
only Django is published to loopback. The separate integration stack's
loopback/trust database is disposable test infrastructure, not a production policy.

Only human-readable backend messages negotiate `en`/`fa`; JSON keys, enum/status
values, URLs, error codes, task/cache/audit names, and other machine contracts
remain stable. Localization must not become an authorization or identity rule.

## Verification and remaining limitations

Tests exercise permission/ownership failures, token rotation/revocation,
password/SMS gating, OTP rollback/redemption and selected real PostgreSQL/Redis
races. Logging tests cover redaction/context scenarios. Default SQLite/LocMem and
eager Celery tests cannot establish real locking, broker delivery, or provider
behavior. CI adds integration tests, Ruff, Bandit, system/migration checks and
artifact validation; a green run is not a vulnerability-free, compliance, or
penetration-testing claim. See [Testing](testing.md).

The current boundaries include:

- No real registered Payment or SMS adapter. Both provider-dependent subsystems
  are disabled by default; contracts/test doubles are not operational integrations.
- Usable OTP codes and sensitive broker payloads in Redis/AOF; no distributed
  transaction with PostgreSQL and no durable reconstruction of lost temporary
  throttle history.
- Shared Redis capacity/availability across caches and task transport; AOF and
  named volumes are not backups. `noeviction` can reject writes under capacity
  pressure rather than discarding security state.
- Non-transactional storage/broker/provider effects and workflow-specific recovery;
  no claim that all races, orphaned files, or ambiguous external outcomes resolve
  automatically.
- No repository-managed host monitoring/alerting, backup automation/storage,
  verified restore drills, managed object storage, or automated dependency-
  vulnerability monitoring platform. Existing-deployment migration compatibility
  and provider-specific enablement require separate review.
- Logging minimization has the scope and UUID-encoding limitation described above;
  it is not a universal secret-leak prevention guarantee.

Report suspected vulnerabilities privately to the repository maintainer. Review
security-sensitive changes against actual authorization, validation, data,
transaction, proxy, cache, logging, and provider boundaries before release.
