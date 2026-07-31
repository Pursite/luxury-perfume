# Authentication

## Overview

The project supports two authentication methods:

1. username and password
2. phone number and one-time password

A valid user may have:

- only a username
- only a phone number
- both a username and a phone number

An active user must have at least one identity.

Authentication uses JSON Web Tokens through Simple JWT.

Successful authentication returns:

- an access token
- a refresh token

Profile completion is separate from authentication and does not block login or token issuance.

---

## Custom User Model

The project uses a custom user model based on:

```python
AbstractBaseUser
PermissionsMixin

The main identity fields are:

username
phone_number

Both fields are optional individually, but an active account must have at least one of them.

Valid accounts:

username only
phone number only
username and phone number

Invalid active account:

no username
no phone number

The model protects this rule through:

model validation
the custom user manager
a database check constraint

The current user manager also calls full_clean() before saving, so manager-created users receive model and field validation as well.

Username Normalization

Usernames are normalized by trimming leading and trailing whitespace.

Stored casing is preserved.

For example:

Armin

remains stored as:

Armin

The project does not automatically convert stored usernames to lowercase.

This preserves compatibility with existing accounts.

Username availability checks and authentication lookups are case-insensitive.

Therefore:

Armin
armin
ARMIN

are treated as the same login identity during lookup.

If legacy data contains multiple usernames differing only by case, authentication should fail safely instead of selecting an arbitrary account.

Phone Number Normalization

Phone numbers are currently normalized by trimming leading and trailing whitespace.

The accepted format is:

09xxxxxxxxx

Example:

09123456789

The current implementation does not automatically convert international formats such as:

+989123456789
00989123456789

Clients should submit the local canonical format expected by the serializer and model validator.

Password Handling

Passwords must never be stored as plain text.

When a password is supplied, the custom user manager uses Django's password API:

user.set_password(password)

This stores a secure password hash.

When no password is supplied, the manager uses:

user.set_unusable_password()

This is used for OTP-created accounts that do not initially support password login.

A user with an unusable password cannot authenticate through the username/password flow until a usable password is explicitly set.

Superusers must have a usable password.

JWT Authentication

The project uses Simple JWT.

Protected requests send the access token through the HTTP Authorization header:

Authorization: Bearer <access-token>

The project supports:

access tokens
refresh tokens
refresh-token rotation
refresh-token blacklisting
logout blacklisting

Token lifetimes are configurable through environment variables:

JWT_ACCESS_TOKEN_LIFETIME_MINUTES=20
JWT_REFRESH_TOKEN_LIFETIME_DAYS=30

Access tokens are intentionally short-lived.

Refresh tokens live longer and are used to obtain new access tokens.

Permission Strategy

The global Django REST Framework permission is:

IsAuthenticated

This means API endpoints are protected by default.

An endpoint is public only when its view explicitly declares:

permission_classes = (AllowAny,)

Public authentication endpoints include:

username/password signup
signup OTP request
signup OTP verification
username/password login
login OTP request
login OTP verification
password-reset OTP request
password-reset verification

Protected endpoints include:

profile completion
profile updates
logout
Username and Password Signup

Endpoint:

POST /users/signup/

The signup flow is:

Request
    ↓
Input serializer
    ↓
Signup service
    ↓
Custom user manager
    ↓
Model validation
    ↓
Password hashing
    ↓
User saved
    ↓
JWT tokens returned

The account can be created with a username and password.

A successful signup returns JWT tokens immediately.

The user does not need to complete optional profile fields or create an address before logging in.

Username and Password Login

Endpoint:

POST /users/login/userpass/

Example request:

{
  "username": "example",
  "password": "secret"
}

The flow is:

validate the request
normalize the username
identify the client IP
check the password-login guard
perform a case-insensitive username lookup
verify the password hash
verify that the user is active
clear the matching failed-attempt state
generate JWT tokens

The login service receives both the username and client IP and creates a password-login guard scoped to that pair.

Authentication failures use a generic message.

The API must not reveal whether:

the username exists
the password is wrong
the account is inactive
the account has an unusable password
Password Login Protection

Repeated password failures are stored in the security cache.

The lock state is scoped by:

normalized username
client IP address

This means:

the same username from different IPs has separate failure state
different usernames from the same IP have separate failure state
a successful login clears only the matching username/IP state

The endpoint also uses a DRF throttle.

These protections serve different purposes:

DRF throttling limits request frequency
the password guard tracks repeated credential failures

Configuration:

PASSWORD_LOGIN_MAX_ATTEMPTS=5
PASSWORD_LOGIN_LOCK_SECONDS=300
PASSWORD_LOGIN_THROTTLE_RATE=10/m

When the maximum failure count is reached, that username/IP pair is temporarily locked.

Security-cache failures fail closed.

This means the API returns a temporary service-unavailable response rather than allowing login protection to be bypassed.

Phone and OTP Signup

The signup OTP flow uses two endpoints:

POST /users/signup/send-otp/
POST /users/signup/verify-otp/
OTP request

The client submits a phone number.

The service:

normalizes the phone number
generates a six-digit OTP using a cryptographically secure generator
stores the OTP in the security cache
queues a Celery task
returns the OTP expiry time

Conceptual flow:

Phone number
    ↓
Generate OTP
    ↓
Store OTP in Redis
    ↓
Queue Celery task
    ↓
Send message
OTP verification

The client submits:

{
  "phone_number": "09123456789",
  "otp": "123456"
}

The service:

normalizes the phone number
checks the temporary lock state
acquires a short verification lease
loads the stored OTP
compares the submitted and stored codes
records failed attempts when invalid
consumes the OTP when valid
creates the user
returns the expected response

OTP-created users may initially have an unusable password.

Phone and OTP Login

The login OTP flow uses:

POST /users/login/send-otp/
POST /users/login/verify-otp/
Sending a login OTP

The request provides a phone number.

For an existing account, the service:

generates an OTP
stores it in the security cache
queues the SMS task
returns a generic success response

For a nonexistent account, the API returns the same externally visible response.

This reduces account enumeration.

The current login OTP service deliberately returns a generic request response when the phone number does not exist.

Verifying a login OTP

The service:

normalizes the phone number
verifies and consumes the OTP
loads the user
confirms that the account is active
generates access and refresh tokens

Invalid, expired, or reused codes return a generic OTP error.

OTP Namespaces

OTP state is separated by purpose.

Current purposes include:

signup
login
password reset

A code created for one purpose cannot be used for another.

Conceptual Redis keys:

security:otp:signup:<phone>:code
security:otp:login:<phone>:code
security:otp:password-reset:<phone>:code

Each purpose has separate:

OTP value
failed-attempt counter
temporary lock state
verification lease
OTP Failure Protection

OTP verification tracks invalid attempts.

Configuration:

OTP_EXPIRY_SECONDS=120
OTP_VERIFICATION_MAX_ATTEMPTS=5
OTP_VERIFICATION_LOCK_SECONDS=300
OTP_VERIFY_THROTTLE_RATE=10/m

When the maximum number of failed attempts is reached, verification is temporarily locked.

Successful verification clears:

the OTP
failed-attempt state
temporary lock state

A successfully consumed OTP cannot be reused.

A short verification lease reduces concurrent verification attempts for the same OTP.

Password Reset

The password-reset flow uses:

POST /users/password-reset/send-otp/
POST /users/password-reset/verify-and-reset/

The flow is:

Phone submitted
    ↓
Generic OTP request response
    ↓
OTP sent for eligible account
    ↓
OTP and new password submitted
    ↓
OTP verified and consumed
    ↓
New password validated
    ↓
Password hash updated

The OTP request response must not reveal whether the phone number exists.

The new password must be stored using Django's password-hashing API.

Profile Completion

Profile completion is separate from authentication.

The is_profile_complete property may depend on:

username
email
first name
last name
at least one address

This property is informational only.

An incomplete profile must not block:

username/password login
OTP login
JWT issuance
token refresh

Authenticated users can complete or update their profile later.

Logout

Endpoint:

POST /users/logout/

The client submits a refresh token.

The logout service blacklists that token.

After logout:

the submitted refresh token cannot be reused
an existing access token remains valid until expiry

This is one reason access tokens use a relatively short lifetime.

Refresh Token Rotation

Refresh-token rotation is enabled.

When a refresh token is used:

a new refresh token is generated
a new access token is generated
the previous refresh token is blacklisted

Clients must replace the stored refresh token after every successful refresh.

Authentication Errors

Authentication responses should remain generic.

The API must not reveal:

whether a username exists
whether a phone number exists
whether an account is inactive
whether an account uses OTP only
whether a password is unusable
internal cache details
database details

Possible status codes include:

400 validation error
401 authentication failure
429 throttle or temporary lock
503 security cache unavailable

The exact API response structure should remain stable.

Security Cache

Authentication protection state uses a dedicated Redis cache.

This cache is fail-closed.

If Redis cannot safely read or update authentication state, the request fails temporarily.

This prevents the application from silently disabling:

OTP attempt limits
OTP replay protection
password-login lockouts

Ordinary application caching may use different failure behavior.

Client Responsibilities

Clients should:

store access and refresh tokens securely
send access tokens using the Bearer scheme
replace refresh tokens after rotation
handle 429 responses without immediate repeated retries
handle temporary 503 responses
not assume that an OTP request confirms account existence
treat profile completion separately from authentication
Authentication Invariants

The following rules must remain true:

An active user has a username, phone number, or both.
Username/password and phone/OTP login remain supported.
Stored username casing is preserved.
Username lookup remains case-insensitive.
Passwords are always hashed.
OTP-created users may have an unusable password.
OTP codes expire.
OTP codes cannot be reused after successful verification.
OTP purposes remain isolated.
Authentication errors do not reveal account existence.
Profile completion does not control login eligibility.
Protected endpoints require JWT authentication by default.