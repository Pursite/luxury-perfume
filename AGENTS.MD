Security is the highest priority in this repository.

For every change:

- preserve existing behavior and API compatibility unless explicitly requested otherwise
- consider authentication, authorization, data integrity, secrets, logging, uploads, concurrency, and failure behavior
- prefer the smallest secure and testable implementation
- preserve existing user changes and avoid unrelated refactors
- never expose or log passwords, OTPs, JWTs, credentials, or sensitive internal errors
- use relevant Superpowers skills and sub-agents when they clearly improve implementation or review; do not wait indefinitely for stalled agents
- run relevant tests and checks before claiming completion

After meaningful changes, briefly explain:

1. what changed
2. why it changed
3. how it works
4. security and maintainability benefits
5. tradeoffs or compatibility impact
6. tests and checks actually run

Never claim success without verification. If verification cannot run, report the exact failure and what remains unverified.