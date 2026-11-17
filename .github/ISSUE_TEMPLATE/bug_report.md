---
name: Bug report
about: Report a defect with reproduction steps or observed failure conditions.
---

**Security:** Do not disclose suspected vulnerabilities, credential leaks, or
sensitive exploit evidence in a public Issue. Follow
[CONTRIBUTING.md](https://github.com/Pursite/luxury-perfume/blob/main/CONTRIBUTING.md)
and [Security](https://github.com/Pursite/luxury-perfume/blob/main/docs/security.md).
No dedicated private reporting address or configured private advisory route is
documented. If no private contact is visibly available, request private reporting
instructions without disclosing vulnerability details.

Use a descriptive issue title. Complete only relevant details; unknown values
can be omitted or marked N/A. A root-cause diagnosis or proposed fix is not required.

## Bug description

What is wrong, and which behavior or workflow is affected?

## Affected component

Area(s), if known: Backend/API; Authentication/JWT/OTP/authorization;
Products/Catalogue; Cart/Orders; Payments/Notifications; PostgreSQL/Redis/Celery
worker or Beat; Frontend/React; Docker/Development; Tests/CI;
Deployment/Documentation; Other/Unknown.

SMS and Payments are disabled by default without real registered provider
adapters; some frontend capabilities are unavailable. Identify the specific
backend flow or UI control involved; see `frontend/README.md` for current limits.

## Steps to reproduce

1. Starting state/setup (for example, anonymous or signed-in user; use no real identities):
2. Minimal action, sanitized HTTP method/path, or local command:
3. Observe the result:

For intermittent failures, describe frequency, observed conditions, and steps
attempted so far. A deterministic reproduction is not required. No full CI run,
production access, or integration infrastructure is required to submit a report.

## Expected behavior

What should happen?

## Actual behavior

What happened instead? Include the HTTP status, sanitized response structure,
UI message, exception type, or failing test name when available. Do not paste
sensitive raw responses.

## Environment and revision

Include only what applies; unknown/N/A is fine. Share configuration names, not secrets.

- Context: local development, tests/CI, or production; commit SHA/release if known:
- OS and execution: Docker/Compose, host Python, or browser:
- Relevant versions: Python, Node, Docker/Compose, browser:
- Django settings profile/module, if relevant:
- Backend tests: SQLite/LocMem or PostgreSQL/Redis integration:

## Logs and evidence (optional)

Add small, relevant **sanitized** traceback/log excerpts, a failing test name,
GitHub Actions run link, request/response example, screenshot, or short recording.

Do not publish passwords, OTPs, JWT access/refresh tokens, cookies, API/signing
keys, complete `.env` files, database credentials, private user information,
Payment/provider payloads, internal production addresses, or sensitive logs.
Redact evidence before sharing; avoid unbounded log dumps.

## Additional context (optional)

When did this start? Note a workaround, related issue, or suspected cause clearly
labelled as a hypothesis. Distinguish observed facts from assumptions.
