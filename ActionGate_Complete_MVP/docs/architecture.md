# Architecture — ActionGate Gateway MVP

## Request path

```text
User task
   |
   v
Separate demo agent client
   |  POST /v1/tasks (loopback HTTP)
   v
ActionGate Gateway API
   |
   v
Interpret task (Gemini JSON parser or restricted deterministic fallback)
   |
   v
Validate structured action/tool plan against local allowlists
   |
   v
Inspect actual database/file impact
   |
   v
Deterministic policy: ALLOW / HOLD / BLOCK
   |               |             |
   |               |             +--> refuse and audit
   |               +--> reviewer-bound approval and explicit confirmation
   +--> user confirms read-only execution
                   |
                   v
Revalidate action, impact, approval and expiry
                   |
                   v
Allowlisted executor only (database / scoped workspace / optional SMTP)
                   |
                   v
Hash-chained audit event history
```

## Components

- **Gateway API:** local HTTP entry point; accepts bounded JSON request bodies; exposes task, approval, execution, health and event endpoints; loopback only.
- **Demo agent:** a separate console client that sends requests to the gateway. It does not have tools to access SQLite, operate on files, send emails, or run shell commands directly.
- **Gemini client and interpreters:** convert an untrusted natural-language task into constrained JSON. A narrow deterministic fallback supports a small subset of tasks. Unknown tasks fail closed.
- **Schema validator:** allowlists agents, operations, tables, columns, filters, and values.
- **Impact inspector:** derives affected record keys/count/digest from the database or inspects the exact target in the scoped file workspace.
- **Policy engine:** deterministically returns ALLOW, HOLD or BLOCK. Model output cannot override a policy block.
- **Approval service:** binds approvals to exact action/impact, policy version, expiry and single-use state. A separate reviewer label is required; the label is not authenticated.
- **Execution services:** revalidate impact and use only allowlisted operations. File deletion is recoverable quarantine; email requires SMTP configuration.
- **Audit service:** application append API and SHA-256 hash-chain verification.
- **Streamlit dashboard:** reviewer/inspection interface; not itself the gateway enforcement boundary.

## Trust and limitations

1. Task text and model output are untrusted.
2. Only the gateway may invoke the allowlisted executors in the demo workflow.
3. The deterministic policy is the final authorization authority.
4. Demo identities do not authenticate users. Pending HTTP requests are held in process memory and are lost on service restart.
5. HTTP API binds to loopback by default. Do not expose it to another device or the internet.
6. A hash chain detects some edits and reordering but cannot prevent privileged deletion or reliable detection of all tail truncations.
7. This is a local hackathon MVP, not a production security gateway.
