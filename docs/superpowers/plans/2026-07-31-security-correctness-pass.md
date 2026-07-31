# Focused Security and Correctness Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden authentication, authorization, media validation, and category integrity while preserving the current API architecture and contracts.

**Architecture:** Security controls live in focused cache/throttle helpers and are consumed by the existing user services. Views declare endpoint intent and map only domain conflicts; serializers validate request data; services retain business writes. Models hold persistent invariants.

**Tech Stack:** Django 6, Django REST Framework, Simple JWT, django-redis cache API, Pillow, pytest-django.

## Global Constraints

- Preserve API routes and JWT response format.
- Global DRF permission is `IsAuthenticated`; every public API view declares `AllowAny`.
- Preserve username/password and phone/OTP account flows.
- Do not alter logging design, JWT bearer authentication, or product thumbnail behavior.
- Security cache failures must fail closed; ordinary product caching may remain fail-open.

---

### Task 1: Establish executable test environment and baseline

**Files:**
- Modify: `requirements.txt`
- Test: existing pytest suites

- [ ] Add or install the repository test dependencies, retaining one PostgreSQL driver distribution.
- [ ] Run `pytest` and record pre-existing failures separately.

### Task 2: Identity model and authentication correctness

**Files:**
- Modify: `apps/users/models.py`, `apps/users/selectors.py`, `apps/users/services/signup_service.py`, `apps/users/services/login_otp_service.py`, `apps/users/services/user_auth_service.py`, `apps/users/serializers.py`
- Create: migration under `apps/users/migrations/`
- Test: `apps/users/tests/test_user_model.py`, `apps/users/tests/test_signin_flow.py`, `apps/users/tests/test_signup_flow.py`, `apps/users/tests/test_profile_flow.py`

- [ ] Write failing tests for each supported identity combination, password usability, safe string conversion, immediate login, and profile-complete state.
- [ ] Enforce identity and normalization invariants in model/manager/services; map integrity conflicts safely.
- [ ] Remove profile completion as an authentication precondition and remove broad profile update exception handling.
- [ ] Run focused user tests.

### Task 3: OTP verification and password-login defenses

**Files:**
- Modify: `apps/lib/cache.py`, `apps/lib/throttle.py`, `apps/users/services/signup_otp_service.py`, `apps/users/services/login_otp_service.py`, `apps/users/services/pass_reset_service.py`, `apps/users/views.py`, `config/settings.py`
- Test: `apps/users/tests/test_signup_flow.py`, `apps/users/tests/test_signin_flow.py`, `apps/users/tests/test_pass_reset_flow.py`

- [ ] Write failing tests for OTP correctness, expiry, replay, lockouts, namespace isolation, counter reset, unavailable security cache, and password-login failure throttling.
- [ ] Implement an atomic, fail-closed OTP guard with per-purpose/phone keys and a verification throttle.
- [ ] Implement temporary identity login locks and clear them on successful login.
- [ ] Run focused authentication security tests.

### Task 4: Permission audit and reusable media/category validation

**Files:**
- Modify: `apps/products/views.py`, `apps/products/serializers.py`, `apps/products/models.py`
- Create: `apps/lib/image_validation.py`
- Test: `apps/products/tests/test_views.py` and new focused product/model tests

- [ ] Write failing authorization, category-cycle, and image content/filename tests.
- [ ] Make every public product endpoint explicit; retain staff-only mutation access.
- [ ] Reuse strict image validation across product, category, and brand serializer paths.
- [ ] Add bounded category parent-chain validation and ensure writes call model validation.
- [ ] Run focused product tests.

### Task 5: Configuration, migration, and full verification

**Files:**
- Modify: `config/settings.py`, `.env.example`, `requirements.txt`
- Test: full suite

- [ ] Add environment-backed JWT, OTP, verification lock, and throttle values while keeping rotation/blacklisting.
- [ ] Remove redundant `psycopg`/`psycopg-binary` dependency without breaking local installs.
- [ ] Run `pytest`, `python manage.py check`, and `python manage.py makemigrations --check --dry-run` under test settings.
