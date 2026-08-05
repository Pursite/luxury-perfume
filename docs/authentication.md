# Authentication

## Overview

The API supports username/password and phone/OTP authentication through Simple
JWT. Successful signup or login returns an access token and refresh token.
Protected requests use `Authorization: Bearer <access-token>`. All paths below
are relative to `/api/v1/users/`.

## Identities and passwords

An active user needs a non-empty username or phone number. Usernames and email
addresses are trimmed, retain their display casing, and are unique
case-insensitively at the database layer. The migration
`users.0005_customuser_case_insensitive_identities` stops safely before schema
changes if legacy case-conflicting usernames or emails exist; it neither
changes nor reports identity values. An operator must resolve those records
privately and rerun the migration.

Phone input is trimmed and must be exactly `09[0-9]{9}`: eleven ASCII digits
beginning with `09`, for example `09123456789`. Unicode digits, international
forms, and alternate formatting are rejected rather than translated.

Every password entry point—direct signup, profile completion, profile update,
and password reset—uses the same configured Django policy: a 12-character
minimum plus similarity, common-password, and numeric-password validation.
The API also has a 128-character request-size cap for password fields.
Passwords are never logged. OTP-created accounts have an unusable password
until profile completion sets one; superusers require a password.

## JWT lifecycle, refresh, and logout

Access tokens last 20 minutes and refresh tokens 30 days by default, controlled
by `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` and `JWT_REFRESH_TOKEN_LIFETIME_DAYS`.

`POST token/refresh/` accepts `{"refresh": "<refresh-token>"}` and returns
`{"access": "...", "refresh": "..."}`. Refresh rotation and blacklist-after-
rotation are enabled: clients must replace the old refresh token after each
successful response; replaying it is rejected.

Tokens carry Simple JWT's password-hash revocation claim. A password change
(profile completion/update or OTP reset) locks the user record, blacklists all
unexpired outstanding refresh tokens, and invalidates access tokens minted from
the old password. The refresh endpoint validates that claim while holding the
same user-row lock, so it cannot race a password change into a usable session.
After an authenticated profile password update, sign in again to receive new
tokens; password reset already returns newly minted tokens. This intentionally
invalidates JWTs issued before this hardening deployment because they lack the
revocation claim.

`POST logout/` requires an access token and a `refresh` body field. It only
blacklists a valid refresh token whose `user_id` claim belongs to the
authenticated user. Invalid, expired, blacklisted, stale, or another user's
refresh token returns the existing generic 400 validation response.

## Username/password endpoints

`POST signup/` accepts a 5–150 character ASCII-letter/digit/underscore
username and a password. It returns `201` with the minimal username and a
token pair. Case-conflicting and concurrent signup attempts return the existing
generic 400 response.

`POST login/userpass/` accepts `username` and `password`, returning `200` with
a message and a token pair. Lookups are case-insensitive and all absent,
inactive, unusable-password, and incorrect-password cases return the same 401
error. Absent and legacy-ambiguous username paths perform a dummy password hash
before returning, reducing practical timing enumeration. A separate security
cache guard limits failed attempts by normalized username and trusted client
IP; the endpoint also has the `login` anonymous-IP throttle.

## Phone/OTP flows

Each OTP flow requires canonical `phone_number`; verification also requires an
exactly six-character ASCII-digit `otp`.

```text
Request OTP -> security cache -> placeholder Celery task -> verify -> consume
```

The Celery task remains a placeholder and does not call an SMS provider.

- `POST signup/send-otp/` and `POST signup/verify-otp/` create a phone-only
  account after successful verification.
- `POST login/send-otp/` and `POST login/verify-otp/` issue tokens for an
  active matching user. Unknown-phone request responses remain generic.
- `POST password-reset/send-otp/` always returns the same request response.
  `POST password-reset/verify-and-reset/` verifies the OTP, applies the shared
  password policy, revokes prior sessions, and returns a new token pair.

Each request and verification endpoint applies two independent limits from the
fail-closed `security` cache: one keyed by normalized phone and one by client
IP. `OTP_REQUEST_THROTTLE_RATE` and `OTP_VERIFY_THROTTLE_RATE` retain the
phone-limit settings; `OTP_REQUEST_IP_THROTTLE_RATE` and
`OTP_VERIFY_IP_THROTTLE_RATE` configure IP limits. A cache outage returns 503,
not an unthrottled request. Production trusts one host-managed proxy via
`DRF_NUM_PROXIES=1`; do not expose Gunicorn directly or increase this value
without matching trusted proxy topology.

OTP state is separated by `signup`, `login`, and `password-reset` purposes.
`OTP_EXPIRY_SECONDS`, `OTP_VERIFICATION_MAX_ATTEMPTS`, and
`OTP_VERIFICATION_LOCK_SECONDS` govern expiry and the additional per-phone
verification lock. Verification uses a short security-cache lease and
constant-time comparison; Redis provides atomic lease acquisition, but the
multi-key verification sequence is not a Redis transaction.

## Profile behavior

Profile completion and update require JWT authentication but do not otherwise
block login or refresh. Completion sets username, email, name, password, and a
first address. Update accepts any subset of `username`, `first_name`,
`last_name`, and `password`; it does not accept email or addresses. Responses
keep the existing `data` user representation. A password-bearing completion or
update has the session-revocation behavior described above.
