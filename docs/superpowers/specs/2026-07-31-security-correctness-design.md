# Focused Security and Correctness Pass

## Goal

Harden the existing Django REST API without changing routes, response token shapes, or the present views/serializers/services/selectors layering.

## Design

- Retain global DRF `IsAuthenticated`; public views explicitly declare `AllowAny`. Product reads remain public and writes remain staff-only.
- Add a small security-sensitive cache guard for OTP verification and username/password login failures. It uses purpose- and phone-namespaced keys, atomic cache primitives where available, consumes a successful OTP before database work, and raises a temporary-unavailable API error if cache state cannot be safely determined.
- Preserve username/password and phone/OTP accounts. Enforce a model and service invariant that an active user has a username or phone number, retain optional fields, normalize identities, and handle uniqueness races as generic conflicts.
- Permit active password users to authenticate immediately after signup. `is_profile_complete` remains an informational property based on profile data and an address.
- Extract the existing product-image checks into reusable serializer validation used by product images, category images, and brand logos. Add model-level category-cycle validation.
- Configure JWT, OTP, and throttle values through environment variables with secure development defaults. Keep refresh rotation and blacklist behavior.

## Error Handling and Tests

Views remain thin. Services raise domain-specific DRF exceptions; profile updates no longer catch unexpected exceptions. Focused pytest coverage will prove permissions, OTP lifecycle/lockouts/failure behavior, account invariants, login behavior, profile conflicts, image validation, category hierarchy, and configuration-dependent behavior.
