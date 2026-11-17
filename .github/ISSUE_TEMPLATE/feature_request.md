---
name: Feature request
about: Propose a user-focused capability or improvement and its desired outcome.
---

Describe the problem and desired outcome in plain language. Technical design,
estimates, and an implementation owner are not required; omit unknown or
irrelevant details. A request starts a discussion, not a delivery commitment.

## Problem or opportunity

What problem should this solve, who is affected, and where does the current
behavior fall short? A concrete use case helps.

## Proposed behavior

What should a user or API client be able to do? Describe the intended behavior
without needing code or an architecture plan.

## Example use case (optional)

Show a short API or storefront workflow illustrating the desired result.

## Expected outcome / acceptance criteria

Suggest a few observable conditions for completion; these are proposed criteria
for discussion, not commitments.

- User/API capability:
- Expected response or UI behavior:
- Important edge cases, if known:

## Alternatives or workarounds (optional)

What do you do today, or what other approaches have you considered?

## Scope and affected areas

Area(s), if known: Backend/API; Authentication; Products/Catalogue; Cart/Orders;
Payments/Notifications; Frontend/UI; Database/concurrency; Infrastructure/CI;
Documentation; Other/Unknown.

Is this new functionality, a change to existing backend behavior, provider/
configuration enablement, or frontend exposure of an existing backend capability?
Unknown is fine.

Payments and SMS are disabled by default with no real registered provider
adapters. Some SMS interactions remain disabled in React, and some backend
capabilities have no completed customer UI. Requests to enable or complete these
flows are welcome; identify the desired outcome without assuming a live service.
See [Frontend](https://github.com/Pursite/luxury-perfume/blob/main/frontend/README.md)
for current UI boundaries.

## Constraints and compatibility (optional)

Mention concerns you know about: existing API compatibility, authentication/user
ownership, security/privacy, data integrity/migrations, performance, background
processing, accessibility, deployment, or external provider dependencies.
You do not need to answer unfamiliar technical questions.

## Additional context (optional)

Add related issues, references, sanitized mockups/screenshots, priority context,
non-goals, or trade-offs. Exclude secrets, private user data, provider payloads,
and internal production addresses. For suspected vulnerabilities, follow
[CONTRIBUTING.md](https://github.com/Pursite/luxury-perfume/blob/main/CONTRIBUTING.md)
to request private reporting instructions without publishing exploit details.
