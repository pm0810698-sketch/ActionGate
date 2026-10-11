# Current Status and Remaining Work

## Implemented in the current local MVP

- Strict structured action schema and agent/table/operation/column allowlists.
- Database-derived affected primary keys, row counts and stable digests.
- Deterministic ALLOW/HOLD/BLOCK policy, including server-side UPDATE row cap and unfiltered UPDATE rejection.
- Scope-bound database approvals, expiry, self-approval checks and single-use consumption.
- Transactional database execution with execution-time impact revalidation.
- SHA-256 hash-chained audit events and chain verification.
- Gemini REST JSON interpreter for database and constrained external tool tasks, with a narrow deterministic fallback.
- Scoped workspace file listing and recoverable quarantine for a single approved file deletion.
- Optional SMTP email tool behind preview/approval/confirmation; requires configured SMTP credentials.
- Loopback HTTP gateway API and separate demo agent client.
- Automated tests across schema, policy, impact, approval, execution, audit, Gemini client/interpreters, tools and gateway.

## Known limitations / future production work

- Demo requester/reviewer names are not authenticated; real identity provider and role-based authorization are needed.
- Requests/approval preview state is held in memory; durable request state and expiry cleanup are needed for deployment.
- Production API needs authentication, rate limiting, TLS, request signing/CSRF controls where relevant, hardened process isolation, and structured operational logging.
- Audit chain needs remote/independent anchoring to improve resistance to database replacement or tail truncation.
- Tool permissions, reversibility classifications, data sensitivity and per-tool rate/impact budgets should be made configurable policy.
- The optional SMTP tool is not required for the core pitch; configure and test only with a controlled recipient.
- No phone calling, arbitrary shell, arbitrary SQL, unrestricted computer-use, or arbitrary file deletion is supported.

## Demo acceptance checklist

1. `Show standard customers` -> ALLOW, preview, confirmation, read executes.
2. `Mark pending orders for review` -> HOLD, separate reviewer approval, explicit confirmation, revalidate and execute.
3. Modify/replay approval -> refusal.
4. `Delete file demo_delete_me.txt` -> target confined to workspace, HOLD, confirm, quarantine rather than permanent erase.
5. Unknown task / agent / tool -> BLOCK, no execution.
6. Force AI fallback: recognized example uses restricted fallback and audit records source; unsupported task blocks.
7. Check `GET /health` and audit chain status.

The current package snapshot was tested before distribution. Re-run `run_tests.ps1` after setup on the target machine.
