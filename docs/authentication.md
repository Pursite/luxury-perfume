# Authentication

## Overview

The API supports username/password and phone/OTP authentication through Simple JWT. Successful signup or login returns an access token and refresh token. Protected requests use:

```http
Authorization: Bearer <access-token>
```

All user endpoint paths in this document are relative to `/api/v1/users/`.

## Identity and passwords

The custom user model permits username-only, phone-only, or combined identities. An active user must have at least one non-empty username or phone number; model validation, the custom manager, and a database check constraint enforce that rule.

Usernames are trimmed, preserve their stored casing, and are looked up case-insensitively. A case-conflicting legacy lookup fails instead of selecting an arbitrary account. Phone numbers are trimmed and must match `^09\d{9}$`: eleven digits beginning with `09`, for example `09123456789`. International forms are not converted or accepted by the serializers.

Passwords use Django's password-hashing API. OTP-created accounts are created with an unusable password, so they cannot use username/password login until a usable password is set (for example during profile completion). Superusers require a password.

## JWT lifecycle and logout

The configured defaults are a 20-minute access token and a 30-day refresh token, controlled by `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` and `JWT_REFRESH_TOKEN_LIFETIME_DAYS`.

Refresh-token rotation and `BLACKLIST_AFTER_ROTATION` are enabled. After a successful refresh, the client must replace the stored refresh token; the old token is blacklisted. `POST logout/` blacklists the submitted refresh token. Access tokens already issued remain valid until their normal expiry.

## Public username/password endpoints

### Signup

`POST signup/` accepts a username and password. The username is 5–150 ASCII letters, digits, or underscores; the password is 12–128 characters and is checked by Django's password validators.

```json
{
  "username": "armin",
  "password": "a-long-unique-password"
}
```

On `201 Created`, the response is:

```json
{
  "user": {"username": "armin"},
  "tokens": {"refresh": "<refresh-token>", "access": "<access-token>"}
}
```

The endpoint is public and has the `signup` anonymous-IP throttle. Duplicate/competing identity creation is returned as a generic 400 error.

### Login

`POST login/userpass/` accepts `username` and `password` and returns `200 OK` with a message and `tokens` object:

```json
{
  "username": "armin",
  "password": "a-long-unique-password"
}
```

```json
{
  "message": "successfully logged in.",
  "tokens": {"refresh": "<refresh-token>", "access": "<access-token>"}
}
```

Username lookup is case-insensitive and authentication failures use the same generic error for an absent user, unusable/wrong password, inactive user, or ambiguous legacy case conflict. A security-cache guard scopes failed attempts and temporary locks by normalized username plus client IP. A successful login clears only that pair's guard state. The endpoint also has the `login` anonymous-IP throttle.

## Phone/OTP flows

Each OTP flow requires `phone_number`; verification also requires an exactly six-character `otp`. The verification serializer does not require the OTP characters to be numeric, although generated codes are six digits.

```text
Request OTP → store code in the security cache → queue Celery task → verify code → consume code
```

The Celery task is required to process queued OTP delivery, but its current implementation is a placeholder and does not call an SMS provider.

### Signup

- `POST signup/send-otp/` is public, takes `{"phone_number": "09123456789"}`, and returns `200 OK` with `{"message": "Verification code sent successfully.", "expires_in": 120}` using the configured expiry value. Existing-phone requests receive the same response.
- `POST signup/verify-otp/` is public, takes `phone_number` and `otp`, and returns `201 Created` with `{"message": "signup confirmed.", "tokens": {...}}`. It creates a phone-only account with an unusable password.

### Login

- `POST login/send-otp/` is public and returns `200 OK` with `{"message": "otp code successfully sent.", "expires_in": 120}`. It returns that same response for a nonexistent phone number, without creating/storing a code.
- `POST login/verify-otp/` is public and returns `200 OK` with the standard login message and `tokens` object for an active matching user.

### Password reset

- `POST password-reset/send-otp/` is public and returns `200 OK` with `{"message": "password reset otp code successfully sent.", "expires_in": 120}` regardless of account existence.
- `POST password-reset/verify-and-reset/` is public, accepts `phone_number`, `otp`, and `password`, then returns `200 OK` with `{"message": "password changed successfully.", "tokens": {...}}` for an active matching user. Its password is 6–18 characters and must contain an ASCII letter, digit, and one of `!@#$%^&*()`.

OTP state is namespaced by `signup`, `login`, or `password-reset`, so a code cannot cross purposes. `OTP_EXPIRY_SECONDS`, `OTP_VERIFICATION_MAX_ATTEMPTS`, and `OTP_VERIFICATION_LOCK_SECONDS` control expiry, failed-attempt threshold, and lock duration. Invalid attempts increment a per-purpose/phone counter; reaching the threshold temporarily locks verification. A valid verification removes the code, attempts, and lock state, preventing ordinary replay.

Verification acquires a five-second cache lease before reading and consuming the code. This reduces concurrent replay risk; it is not a fully atomic Redis transaction. Security-cache failures fail closed with `503 Service Unavailable`; invalid/expired/reused codes return a generic validation error, and locks or verification throttling return `429 Too Many Requests`.

## Profile behavior

Profile completion and updates require JWT authentication. They are informational and do not block login, token issuance, or token refresh.

`POST profile/complete/` requires `username`, `password`, `email`, `first_name`, `last_name`, and an `address` object with `title` and `full_address` (optional `postal_code`). It sets a usable password, updates the supplied profile fields, creates the address, and returns `200 OK` with the serialized user under `data`.

`PATCH profile/update/` accepts any supplied subset of `username`, `first_name`, `last_name`, and `password`; it does not accept email or addresses. The response is `200 OK` with the updated serialized user under `data`. User output fields are `id`, `phone_number`, `username`, `email`, `first_name`, `last_name`, `is_profile_complete`, and `addresses`.
