# Architecture

## Overview

This project is a Django 6 and Django REST Framework backend for a wine shop API.

The codebase follows a layered architecture that separates:

- HTTP handling
- request validation
- business logic
- database reads
- persistence rules
- background tasks
- shared infrastructure

The current main applications are:

- `apps.users`
- `apps.products`
- `apps.lib`

The project currently uses:

- Django
- Django REST Framework
- PostgreSQL
- Redis
- Celery
- Simple JWT
- Pytest

---

## Project Structure

```text
wine-shop/
├── apps/
│   ├── lib/
│   ├── products/
│   └── users/
├── config/
├── docs/
├── manage.py
├── requirements.txt
└── .env.example
apps.users

Responsible for:

username/password signup
phone/OTP signup
username/password login
phone/OTP login
password reset
user profile completion
user profile updates
user addresses
logout and refresh-token blacklisting
apps.products

Responsible for:

products
categories
brands
product images
public catalogue reads
staff-only catalogue mutations
category hierarchy integrity
image upload validation
apps.lib

Contains shared infrastructure and reusable components, including:

base models
pagination
logging helpers
throttles
security cache guards
reusable image validation

Code should be placed in apps.lib only when it is genuinely shared across multiple applications or represents project-wide infrastructure.

Request Flow

A normal API request should move through the following layers:

Client request
    ↓
APIView
    ↓
Input serializer
    ↓
Service or selector
    ↓
Model and database
    ↓
Output serializer
    ↓
HTTP response

Each layer has a distinct responsibility.

Views

Views are responsible for HTTP orchestration.

A view should usually:

receive the request
validate input using a serializer
call a service or selector
serialize the result
return an HTTP response

Views should remain thin.

They should not contain:

complex business workflows
large ORM queries
password or OTP logic
cache coordination
transaction-heavy mutation logic

Authentication views in the users application follow this pattern by validating request data, calling the appropriate service, and returning the resulting response.

Serializers

Serializers are responsible for:

validating request payloads
normalizing input
validating individual fields
representing model data in API responses
coordinating reusable field-level validation

Examples include:

validating phone numbers
validating usernames and passwords
validating profile updates
validating uploaded product images

Serializers should not become the main location for multi-step business workflows.

Services

Services contain business logic and state-changing operations.

Examples include:

creating a user
sending signup OTP codes
verifying login OTP codes
authenticating username/password users
resetting passwords
updating profiles
blacklisting refresh tokens

A service may coordinate:

models
selectors
cache guards
Celery tasks
transactions
logging

Business rules should be centralized in services or models instead of being duplicated across views.

Selectors

Selectors contain reusable read-oriented database queries.

Examples include:

finding a user by phone number
checking whether a username already exists
performing case-insensitive username lookup
retrieving products
retrieving categories or brands

Selectors should normally avoid mutations.

Their purpose is to keep ORM query logic reusable and out of views.

Models

Models define persisted state and database relationships.

They are also responsible for invariants that must remain valid regardless of how data is written.

Examples include:

requiring an active user to have a username or phone number
preventing invalid category parent relationships
preserving normalized identity values
defining uniqueness and database constraints

Critical invariants should be enforced at both application and database levels where practical.

Application validation provides useful error messages.

Database constraints provide a final integrity boundary.

Background Tasks

Celery is used for work that should not block an API request.

The current main background operation is OTP delivery.

Conceptual flow:

API request
    ↓
Service generates OTP
    ↓
OTP is stored in Redis
    ↓
Celery task is queued
    ↓
Worker sends the message

The HTTP response should not wait for the external messaging provider to finish.

Services queue tasks.

Tasks perform the background operation.

Authentication Boundary

Django REST Framework uses IsAuthenticated as the global default permission.

This means endpoints are protected unless they explicitly declare AllowAny.

Public authentication endpoints explicitly use AllowAny.

Public catalogue reads remain accessible without authentication.

Catalogue mutation endpoints require authenticated staff permissions.

This approach is fail-safe because newly created endpoints are protected by default.

PostgreSQL

PostgreSQL stores durable application state, including:

users
addresses
products
categories
brands
product images
JWT blacklist records

Database migrations must be committed to Git.

Production-sensitive migrations should be tested against PostgreSQL before deployment.

Redis

Redis has two roles in the project.

Default cache

The default cache is intended for ordinary application caching.

It may fail open where cache availability should not prevent the main request from succeeding.

Security cache

A separate cache alias is used for authentication-sensitive state.

It stores data such as:

OTP codes
OTP failed-attempt counters
OTP lock states
OTP verification leases
password-login failed-attempt counters
password-login lock states

The security cache is fail-closed.

If its state cannot be safely read or updated, the authentication request should fail temporarily instead of bypassing the protection.

The project defines separate default and security cache aliases in settings.

JWT

The project uses Simple JWT for authentication.

It supports:

short-lived access tokens
refresh tokens
refresh-token rotation
refresh-token blacklisting
logout blacklisting

JWT lifetimes are configurable through environment variables.

The API uses the Bearer authentication scheme.

JWT response structures and routes should remain stable unless an explicit API versioning decision is made.

Configuration

Runtime configuration is loaded through django-environ.

The real .env file contains local or deployment-specific values and must not be committed.

.env.example documents the expected configuration keys.

Environment-backed settings include:

Django secret key
database connection
Redis connection
Celery broker and result backend
allowed hosts
CORS origins
JWT lifetimes
OTP expiry
authentication lock limits
throttle rates

The current settings module reads these values and defines safe defaults for many security controls.

Logging

The project separates logs into:

system logs
activity logs
security logs

Logging helpers should be reused instead of introducing unrelated logging systems.

Sensitive values must never be written to logs, including:

passwords
OTP values
access tokens
refresh tokens
secret keys
database credentials
Error Handling

Expected client errors should use appropriate DRF exceptions.

Examples include:

validation errors
authentication failures
throttling
temporary security-cache failure

Unexpected exceptions should reach the standard DRF exception handler.

They should not be converted into misleading 400 Bad Request responses.

Internal exception details must not be exposed to API clients.

Testing

Pytest is the primary test runner.

The current project verifies areas such as:

signup and login
OTP expiry and reuse prevention
authentication lockouts
user identity rules
endpoint permissions
profile updates
category hierarchy
image validation
migration consistency

Use:

venv/bin/python -m pytest
venv/bin/python manage.py check
venv/bin/python manage.py makemigrations --check --dry-run
Architectural Rules

The project follows these rules:

Keep views thin.
Put request validation in serializers.
Put business workflows in services.
Put reusable reads in selectors.
Enforce critical invariants in models and database constraints.
Use Celery for background work.
Use Redis for cache and temporary authentication state.
Treat security-cache failures as fail-closed.
Protect endpoints by default.
Preserve existing API routes and response contracts.
Prefer focused changes over broad rewrites.
Keep unrelated domain logic in separate Django applications.
Future Domains

Future features should be developed in isolated branches and introduced as clearly scoped domains.

Potential future applications include:

inventory
cart
orders
payments
shipping
reviews

New applications should preserve the same separation between:

views
serializers
services
selectors
models
tasks