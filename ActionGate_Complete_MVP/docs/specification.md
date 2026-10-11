# Technical Specification

## 1. Scope
A local demo gateway for proposed actions against fictional SQLite customer/order data. Only explicitly allowlisted operations are supported.

## 2. Action format
An action is a structured object with fields such as:
- `request_id`
- `agent_id`
- `operation`
- `table`
- `filters`
- `requested_by`
- `declared_impact_limit` (optional)

Unknown fields should be rejected unless explicitly added to the schema. Identifiers, operators, columns, and operations must be allowlisted. SQL values must be passed as parameters; never concatenate user-controlled values into SQL.

## 3. Decision outcomes
- `ALLOW`: policy permits the action without additional approval.
- `HOLD`: a separate reviewer must approve the exact action and impact.
- `BLOCK`: action is invalid, unauthorized, unsupported, or violates a hard policy.

Unknown agents and unknown action types fail closed.

## 4. Impact calculation
The gateway independently determines affected records from the database. It records at least the affected-row count and a stable digest of sorted primary keys. The model's claimed impact is never authoritative.

## 5. Approval
An approval is bound to the canonical action, impact digest, policy version, expiry, requester, and approver. The requester cannot approve their own request. An approval is single-use. Any change to the action or impact requires fresh approval.

## 6. Execution
Before mutation, revalidate the stored action, recompute impact, verify the approval, and consume the approval in the same database transaction as the mutation. If validation fails, do not mutate data. The first version supports only local database operations.

## 7. Audit
Record requests, decisions, reasons, interpreter/fallback path, approval events, execution attempts, and outcomes. Use a hash chain to make edits detectable. Document that a hash chain alone does not prevent deletion of the final events or guarantee protection against a privileged attacker.

## 8. AI and fallback
AI may translate supported natural-language requests into the structured action schema. AI output is untrusted and must pass the same validation and policy checks. If AI is unavailable or returns unusable output, use a conservative fallback only for clearly supported patterns; otherwise hold or block. Never bypass deterministic policy.

## 9. Acceptance tests
1. Valid permitted read is allowed.
2. Unknown agent is blocked.
3. Unsupported operation/table/column/operator is blocked.
4. Risky action is held for approval.
5. Requester cannot approve their own action.
6. Modified action cannot use an old approval.
7. Changed impact is detected before mutation.
8. Approval cannot be replayed.
9. A refused action leaves the database unchanged.
10. Audit modification is detected.
11. AI failure does not bypass policy.
12. Audit records whether AI or fallback produced the action.

## 10. Out of scope
Cloud deployment, production authentication, arbitrary SQL, real customer data, external side effects, complex integrations, and a claim of production-grade tamper-proof logging.
