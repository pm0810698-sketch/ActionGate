# ActionGate — Project Idea

## One-line summary
ActionGate is a local authorization gateway that checks proposed AI-agent actions before they can change business data.

## Problem
AI agents may request actions that are too broad, unsafe, unsupported, or different from what a reviewer intended to approve. A normal approval button is not enough if the action's real impact can change before execution.

## Proposed solution
ActionGate converts a request into a constrained action, validates it, independently calculates its impact, and applies deterministic security rules. The result is `ALLOW`, `HOLD`, or `BLOCK`. Risky actions can require a separate reviewer. Before execution, the gateway checks that the action and impact still match the approved request.

## Main differentiator
**Impact-bound approval with execution-time revalidation.** Approval is tied to the exact action and the records it affects. If the action or impact changes, the approval is rejected and fresh authorization is required.

## Initial demo scope
- Fictional customer and order data in a local SQLite database.
- Allowlisted read and mutation operations only.
- Deterministic policy decisions; AI never makes the final authorization decision.
- Human approval for selected risky operations.
- Single-use approvals and refusal of self-approval.
- Hash-chained audit events with integrity verification.
- A test panel for changed actions, changed impact, replay, unknown agents, and AI failure.

## Constraints
- Runs locally on Windows.
- Python, SQLite, Streamlit, and pytest.
- No paid API, cloud service, or GPU required.
- External side effects and real customer data are out of scope for the first version.

## Honest claim boundary
The project combines established security techniques in a focused workflow. It does not claim that authorization rules, approval workflows, hashing, or audit logs are new inventions.
