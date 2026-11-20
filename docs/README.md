# Documentation hub

The [project README](../README.md) introduces Luxury Perfume, feature readiness,
and a quick start. The guides below own current technical contracts and
workflows. The independent React/Vite storefront keeps its client/design guidance
in `frontend/`; contribution resources live at the repository root and in `.github/`.
Historical decisions and plans provide context, not current operational authority.
Implementation and tests ultimately resolve disagreements with documentation.

## Starting points

| Reader | Suggested path |
| --- | --- |
| New contributor | [Contributing](../CONTRIBUTING.md) → [Development](development.md) → [Testing](testing.md) |
| Store operator | [Backoffice](backoffice.md) → [Security](security.md#django-admin-boundaries) |
| Backend/API developer | [Architecture](architecture.md) → [API](api.md) → [Authentication](authentication.md) |
| Frontend developer | [Frontend README](../frontend/README.md) → [Design](../frontend/DESIGN.md) → [API](api.md) |
| Security reviewer | [Security](security.md) → [Authentication](authentication.md) → [Architecture](architecture.md) |
| Release/operations reviewer | [CI/CD](ci-cd.md) → [Deployment](deployment.md) → [Troubleshooting](troubleshooting.md) |
| Recruiter/portfolio reviewer | [Project overview](../README.md) → [Architecture](architecture.md) → [Testing](testing.md) → [CI/CD](ci-cd.md) |

## Canonical technical guides and ownership

Use this table both to find information and to choose which document to update
when behavior changes. Keep implementation-backed explanations with their owner
and cross-link instead of duplicating full instructions.

| Guide | Owns / update when |
| --- | --- |
| [Architecture](architecture.md) | Request layers, domain boundaries, persistence/integrity, concurrency, asynchronous recovery, and runtime design change |
| [Development](development.md) | Local Docker/host setup, environment requirements, management commands, and daily workflow change |
| [API Reference](api.md) | HTTP paths/methods, permissions, request/response contracts, filtering, pagination, or error behavior change |
| [Backoffice](backoffice.md) | Django Admin store workflows, staff roles, and dashboard metrics |
| [Authentication](authentication.md) | Identity, profile, password, OTP, refresh-cookie/JWT lifecycle, or session workflows change |
| [Security](security.md) | Controls, trust boundaries, proxy/cache/throttle policies, logging protections, or known limitations change |
| [Testing](testing.md) | Verification commands, fixtures/isolation, PostgreSQL/Redis integration, frontend checks, or coverage semantics change |
| [Troubleshooting](troubleshooting.md) | Reproducible failure diagnostics and supported corrective actions change |
| [CI/CD](ci-cd.md) | CI jobs/gates, build artifacts, GHCR publication, workflow permissions/secrets, or manual CD orchestration change |
| [Deployment](deployment.md) | VPS preparation, production environment, Nginx/TLS, assets/persistence, health/logs, or recovery operations change |

CI verification, image publication, and production deployment are distinct stages.
The pipeline guide explains how revisions/artifacts move between them; deployment
explains host preparation and operation. Neither establishes that a live host or
external provider is operational.

## Frontend documentation

- [Frontend README](../frontend/README.md): independent React/Vite setup, routes,
  API client, session/Cart ownership, feature availability, accessibility, and checks.
- [Design specification](../frontend/DESIGN.md): visual intent and its runtime CSS
  mapping. Update this for design decisions, while the frontend README owns behavior.

Shared HTTP/authentication contracts belong in API and Authentication; system
trust boundaries belong in Security. Backend functionality may exist without a
completed customer UI or operational provider integration.

## Contribution and GitHub resources

- [CONTRIBUTING.md](../CONTRIBUTING.md): human contribution workflow, expected
  engineering discipline, verification, documentation, and PR preparation.
- [AGENTS.md](../AGENTS.md): detailed instructions for coding agents; it does not
  replace human contribution guidance.
- [Pull Request template](../.github/PULL_REQUEST_TEMPLATE.md): information needed
  to review a specific change, checks, compatibility, risks, and evidence.
- [Bug report template](../.github/ISSUE_TEMPLATE/bug_report.md): observed defects,
  reproduction/intermittency, environment, and sanitized diagnostic evidence.
- [Feature request template](../.github/ISSUE_TEMPLATE/feature_request.md): user
  problems, proposed outcomes, acceptance criteria, alternatives, and constraints.

Update contributor workflow in CONTRIBUTING; keep review/reporting prompts in
their templates. GitHub's chooser uses issue templates from default branch
`main`; templates on this documentation branch are not automatically active there.
Follow contributor/security guidance for suspected vulnerabilities; do not disclose
exploit details or sensitive evidence in public reports.

## Historical decisions and archived plans

The current historical directories contain:

```text
docs/
├── decisions/
│   ├── 2026-08-03-test-suite-improvement-design.md
│   └── 2026-08-06-ghcr-image-deployment-design.md
└── archive/plans/
    ├── 2026-08-03-test-suite-improvement.md
    └── 2026-08-06-ghcr-image-delivery.md
```

[Decisions](decisions/) holds dated design records for test-suite improvements
and GHCR delivery. [Archived plans](archive/plans/) holds the corresponding
implementation plans. They can explain earlier intent and trade-offs, including
superseded paths or assumptions; use canonical guides and current code/tests for
present behavior. They are not deployment runbooks or instructions to repeat
historical changes. Preserve this distinction when adding or updating references.
