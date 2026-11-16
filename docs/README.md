# Luxury Perfume Documentation

This directory contains the technical documentation for **Luxury Perfume**, a production-oriented e-commerce application built with Django REST Framework and an independent React storefront.

The documentation is organized by responsibility so that architecture, API contracts, security behavior, development workflows, testing, and deployment guidance can evolve independently without turning the root project README into a large technical manual.

## Start Here

If you are new to the project, read the documentation in roughly this order:

1. [Project README](../README.md) — project overview, major features, technology stack, and quick start.
2. [Architecture](architecture.md) — system structure, application boundaries, data flow, infrastructure, and background processing.
3. [Development](development.md) — local environment setup and day-to-day development workflow.
4. [Authentication](authentication.md) — identity, OTP, JWT, profile, session, and authentication behavior.
5. [API Reference](api.md) — HTTP endpoints and API contracts.
6. [Testing](testing.md) — backend, integration, frontend, linting, security, and validation checks.
7. [Security](security.md) — implemented security controls, trust boundaries, and known limitations.
8. [Deployment](deployment.md) — production deployment architecture and operational procedures.

## Documentation Index

| Document                              | Purpose                                                                                                                                                                                 |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Architecture](architecture.md)       | Describes the system architecture, Django application boundaries, request layers, persistence, Redis usage, Celery tasks, concurrency model, and frontend separation.                   |
| [API Reference](api.md)               | Documents the public and authenticated HTTP API, request/response contracts, permissions, filtering, pagination, and endpoint behavior.                                                 |
| [Authentication](authentication.md)   | Covers username/password and phone/OTP authentication, JWT lifecycle, refresh-token handling, logout, password reset, profile verification, and account identity rules.                 |
| [Development](development.md)         | Explains local development with Docker Compose or direct-host execution, environment configuration, backend startup, and frontend startup.                                              |
| [Testing](testing.md)                 | Documents unit tests, PostgreSQL/Redis integration tests, frontend tests, coverage, Ruff, Bandit, Django checks, and migration verification.                                            |
| [Security](security.md)               | Describes authentication and authorization controls, validation, throttling, logging protections, cache isolation, uploads, cookies, concurrency protections, and security limitations. |
| [Deployment](deployment.md)           | Covers production configuration, container images, GitHub Actions release flow, VPS deployment, environment handling, static/media assets, and operational constraints.                 |
| [Troubleshooting](troubleshooting.md) | Provides solutions for common development, Docker, database, Redis, Celery, frontend, test, and deployment problems.                                                                    |

## Frontend Documentation

The customer storefront is an independent React/Vite application located in [`frontend/`](../frontend/).

Frontend-specific documentation lives with the frontend source:

* [Frontend README](../frontend/README.md) — development workflow, source structure, browser/API integration, scripts, and runtime behavior.
* [Frontend Design](../frontend/DESIGN.md) — visual language, UI conventions, and design-system guidance.

Backend and frontend documentation should remain separated where their concerns differ. Cross-system behavior should be documented in the most appropriate shared document, usually the architecture, API, security, or deployment documentation.

## Contribution and Repository Guidance

Repository-wide contribution guidance is documented in:

* [CONTRIBUTING.md](../CONTRIBUTING.md) — contributor workflow, development expectations, testing requirements, and pull-request guidance.
* [AGENTS.md](../AGENTS.md) — repository rules and engineering constraints for automated coding agents and repository-assisted development.

`AGENTS.md` is not a replacement for contributor documentation. It defines implementation discipline and repository-specific engineering rules for automated tooling.

## Internal Plans and Specifications

The [`superpowers/`](superpowers/) directory contains implementation planning and specification material used during development.

```text
superpowers/
├── plans/
└── specs/
```

These documents may describe individual changes, implementation plans, or design decisions and should not be treated as the canonical description of current system behavior.

The canonical documentation for the current application remains the documents listed in the main documentation index above.

## Documentation Principles

Documentation in this repository should describe **implemented behavior**, not assumptions, abandoned designs, or intended future behavior presented as current functionality.

When implementation changes, update the relevant documentation in the same change whenever practical.

In particular:

* API changes should be reflected in `api.md`.
* Authentication or identity changes should be reflected in `authentication.md`.
* Application boundaries or infrastructure changes should be reflected in `architecture.md`.
* Security-sensitive changes should be reflected in `security.md`.
* Environment or developer-workflow changes should be reflected in `development.md`.
* Test infrastructure or verification changes should be reflected in `testing.md`.
* Production or release changes should be reflected in `deployment.md`.
* Common recurring operational failures and their verified solutions may be added to `troubleshooting.md`.

Avoid duplicating large sections across multiple documents. Prefer linking to the authoritative document.

## Keeping Documentation Accurate

Before documenting technical behavior, verify it against the current implementation, tests, configuration, database constraints, and API routes.

The source code remains the ultimate authority when documentation and implementation disagree.

Documentation should be updated when changes affect:

* public API contracts;
* authentication or authorization;
* database invariants;
* application ownership or architecture;
* asynchronous tasks or scheduled jobs;
* Redis/cache behavior;
* environment variables;
* testing requirements;
* security guarantees;
* deployment or release procedures.

Historical or proposed behavior should be clearly identified as such rather than being mixed with documentation of the current system.
