# Authentication

## Overview

The API supports username/password and phone/OTP authentication through Simple
JWT. Successful token-issuing responses return an access token in JSON and set
the rotating refresh token in a persistent, host-only `HttpOnly` cookie.
Protected requests use `Authorization: Bearer <access-token>`. All paths below
are relative to `/api/v1/users/`.

## Identities and passwords

An active user needs a non-empty username or phone number. Usernames and email
addresses are trimmed, retain their display casing, and are unique
case-insensitively at the database layer. The migration
history was reset intentionally; the current clean initial migration defines
these constraints and deployments do not carry legacy identity data migrations.

Phone input is trimmed and must be exactly `09[0-9]{9}`: eleven ASCII digits
beginning with `09`, for example `09123456789`. Unicode digits, international
forms, and alternate formatting are rejected rather than translated.

Every password entry point—direct signup, profile update, and password reset—
uses the same configured Django policy: a 12-character
minimum plus similarity, common-password, and numeric-password validation.
The API also has a 128-character request-size cap for password fields.
Passwords are never logged. OTP-created accounts have an unusable password
until the user sets one through profile update; superusers require a password.

## JWT lifecycle, refresh, and logout

Access tokens last 20 minutes and refresh tokens 30 days by default, controlled
by `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` and `JWT_REFRESH_TOKEN_LIFETIME_DAYS`.

`POST token/refresh/` reads the refresh cookie and returns `{"access": "..."}`;
it does not accept or expose a refresh token in JSON. Refresh rotation and
blacklist-after-rotation remain enabled: the response replaces the cookie and
replaying the prior value is rejected. Refresh attempts use a dedicated
fail-closed security-cache throttle (`TOKEN_REFRESH_THROTTLE_RATE`, default
`30/m`) rather than sharing the global anonymous API bucket. Auth responses are
marked `Cache-Control: no-store` (and compatible no-cache headers).

Tokens carry Simple JWT's password-hash revocation claim. A password change
(profile update or OTP reset) locks the user record, blacklists all
unexpired outstanding refresh tokens, and invalidates access tokens minted from
the old password. The refresh endpoint validates that claim while holding the
same user-row lock, so it cannot race a password change into a usable session.
After an authenticated profile password update, sign in again to receive new
tokens; password reset already returns newly minted tokens. This intentionally
invalidates JWTs issued before this hardening deployment because they lack the
revocation claim.

`POST logout/` reads and blacklists the refresh cookie when valid, then expires
that cookie. It is idempotent for missing, invalid, expired, or already
blacklisted cookies and does not require a still-valid access token. Cookie
mutations require an exact trusted `Origin`; CORS preflight (`OPTIONS`) remains
available for explicitly configured storefront origins.

## Username/password endpoints

`POST signup/` accepts a 5–150 character ASCII-letter/digit/underscore
username and a password. The same username limit and character rule apply to
profile onboarding and repeatable profile updates. It returns `201` with the
minimal username, an access token, and a refresh cookie. Case-conflicting and
concurrent signup attempts return the existing generic 400 response.

`POST login/userpass/` accepts `username` and `password`, returning `200` with
a message, an access token, and a refresh cookie. Lookups are case-insensitive and all absent,
inactive, unusable-password, and incorrect-password cases return the same 401
error. Absent and legacy-ambiguous username paths perform a dummy password hash
before returning, reducing practical timing enumeration. A separate security
cache guard limits failed attempts by normalized username and trusted client
IP; the endpoint also has the `login` anonymous-IP throttle.

The React storefront exposes both direct username/password endpoints. Signup
and Login feed the same centralized session handling: access tokens remain in
memory and the refresh cookie is never readable by JavaScript. On every startup,
the app makes one silent refresh attempt before protected providers mount. An
invalid or expired cookie returns the app to `anonymous`; transient refresh
failures such as throttling, network errors, or 5xx responses preserve the
session and expose a retryable restoration-error state instead. Its visible SMS signup and sign-in alternatives are genuinely
disabled and make no OTP request while the external SMS service is unavailable.

Its protected `/account` route keeps profile data and drafts only in React
memory. It reads the authenticated user from `GET profile/`, saves supported
personal and address changes through `PATCH profile/update/`, and replaces its
displayed state from the returned `data`. It does not expose password changes
or call phone-verification, OTP, or password-reset endpoints.

## Phone/OTP flows

Each OTP flow requires canonical `phone_number`; verification also requires an
exactly six-character ASCII-digit `otp`.

```text
Request OTP -> security cache -> placeholder Celery task -> verify -> consume
```

The Celery task remains a placeholder and does not call an SMS provider.

- `POST signup/send-otp/` and `POST signup/verify-otp/` create a phone-only,
  active account after successful verification. Its stored phone number is
  already verified, but the remaining customer profile may be completed later.
- `POST login/send-otp/` and `POST login/verify-otp/` issue tokens for an
  active matching user. Unknown-phone request responses remain generic.
- `POST password-reset/send-otp/` always returns the same request response.
  `POST password-reset/verify-and-reset/` applies account-independent password
  checks before OTP verification. After a matching OTP is proven, it applies
  the full user-aware password policy before consuming the OTP, revokes prior
  sessions, and returns a new access token plus refresh cookie.

Each request and verification endpoint applies two independent limits from the
fail-closed `security` cache: one keyed by normalized phone and one by client
IP. `OTP_REQUEST_THROTTLE_RATE` and `OTP_VERIFY_THROTTLE_RATE` retain the
phone-limit settings; `OTP_REQUEST_IP_THROTTLE_RATE` and
`OTP_VERIFY_IP_THROTTLE_RATE` configure IP limits. The shipped request defaults
allow one request per phone per minute and ten requests per IP per minute, so
the phone limit remains strict without unnecessarily blocking users behind a
shared NAT. A cache outage returns 503, not an unthrottled request. Production
trusts one host-managed proxy via `DRF_NUM_PROXIES=1`; do not expose Gunicorn
directly or increase this value without matching trusted proxy topology.

OTP state is separated by `signup`, `login`, `password-reset`, and the
authenticated-user-bound profile-phone purpose.
`OTP_EXPIRY_SECONDS`, `OTP_VERIFICATION_MAX_ATTEMPTS`, and
`OTP_VERIFICATION_LOCK_SECONDS` govern expiry and the additional per-phone
verification lock. Verification uses a short security-cache lease and
constant-time comparison; Redis provides atomic lease acquisition, but the
multi-key verification sequence is not a Redis transaction. A new OTP replaces
the code only; it never clears failed-attempt state or an active lock. A
successful verification consumes the code, making it single-use.

## Profile behavior

`is_active` is account state only: it represents an enabled or disabled
account, not onboarding progress. Username/password signup creates an active
user immediately and returns tokens even though that user has no verified
phone number or complete customer profile. Incomplete users can browse and use
normal authenticated endpoints. Future checkout-like operations can opt in to
the reusable `IsProfileComplete` permission; it is not applied globally.

`is_profile_complete` is derived rather than stored. It is true only when a
user has a username, a verified phone number, email, first and last
names, and at least one address. Public API flows only persist a profile phone
after `POST profile/phone/send-otp/` followed by successful
`POST profile/phone/verify-otp/`; verification is bound to the authenticated
account, is available only while that account has no verified phone, and
refuses a number owned by another user without revealing that ownership.

`GET profile/` returns only the authenticated user's serialized profile and
ordered addresses. It accepts no user ID, requires authentication, and exposes
no password, token, staff, group, or permission fields.

`POST profile/complete/` is one-time onboarding: it requires the verified
phone, sets username/email/name, and creates the first address. It neither
changes a password nor changes account activation. `PATCH profile/update/` is
repeatable and can update username, email, names, password, and address data.
To edit an existing address it requires that owned address's explicit `id` and
accepts only the address fields being changed, so it never creates duplicates
on repeat edits. Password updates retain the
session-revocation behavior described above; ordinary profile edits do not
revoke access or refresh tokens. Responses keep the existing `data` user
representation.
