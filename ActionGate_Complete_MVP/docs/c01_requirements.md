# C-01 Requirement Traceability

This page maps the challenge requirements to the local MVP without claiming features that are not implemented.

| C-01 requirement | Current MVP coverage | Limit / evidence |
|---|---|---|
| Every proposed action passes through a gateway | Separate demo agent uses the loopback HTTP API | This is the demo integration pattern; no real third-party agent SDK is integrated yet. |
| Every action is ALLOW, BLOCK, or HOLD | Deterministic policy in `app/policy.py`; service returns a decision | Only allowlisted database and the implemented file/email tools are supported. Unknown tasks are blocked. |
| Unknown agents/action types fail closed | `app/schema.py` allowlists agent IDs, operations, tables, columns and filters; external tools have a fixed tool allowlist | Allowlisted agent identities are demo labels, not authenticated principals. |
| Permissions, impact, reversibility and policy make the final call | Database/file impact inspection and deterministic policy; side effects have approval/confirmation | Reversibility rules are narrow and hard-coded for this demo, not a general policy authoring framework. |
| Exact-action approval; changed action reauthorized | Canonical action/tool data, impact digest, count, policy version, expiry, single-use consumption and pre-execution revalidation | Pending gateway requests are currently in memory and are cleared if the process restarts. |
| Requester cannot approve their own request | Identity normalization and self-approval check | Demo reviewer names are not authenticated; production requires a trusted identity provider. |
| Record every decision/refusal in tamper-detectable history | Gateway event logging plus hash-chained SQLite audit events | A privileged user can replace the DB or truncate the audit tail; remote anchoring is future work. |
| Safe if AI unavailable/unusable, record which path decided | Restricted deterministic fallback or BLOCK, with interpreter source in gateway events | Fallback recognizes a small set of phrases only; unsupported tasks deliberately fail closed. |

## How to demonstrate compliance

1. `Show standard customers` → ALLOW → explicit confirmation → read result.
2. `Mark pending orders for review` → HOLD → separate reviewer label → explicit confirmation → impact revalidation → execution.
3. Altered/expired/replayed approval or drifted impact → refusal.
4. `Delete file demo_delete_me.txt` → path within `data/workspace` → HOLD/confirmation → recoverable quarantine.
5. Unknown task such as `Call Samarth` → BLOCK because no call tool exists.
6. Force fallback: known phrase is interpreted by the deterministic parser; unknown phrase is blocked. Show the logged `decision_source`.
7. Check `GET /health` and `GET /v1/events` for chain validity and event provenance.
