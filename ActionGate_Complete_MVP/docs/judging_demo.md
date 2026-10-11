# C-01 Judge Demo Script (3 minutes)

## Pitch

“AI agents can now take actions, not just answer questions. But broad tool permissions do not answer whether a specific action, with its arguments and real impact, is safe right now. ActionGate is an authorization gateway between the agent and the tools. The agent proposes; ActionGate decides; execution happens only through allowlisted tools after the gateway's checks.”

## Live sequence

1. **Show an authorized read.** In the demo agent enter `Show standard customers`. Show the `gemini_llm` or fallback source, ALLOW reason, row count/digest, ask for explicit confirmation, and show the records returned.
2. **Show a risky change.** Enter `Mark pending orders for review`. Show exact impact and HOLD, enter a separate reviewer label, approve, confirm execution, and show the result.
3. **Show scope binding.** Use tests or the approval tests to demonstrate an altered action, replay, and impact drift are refused.
4. **Show a real local side effect safely.** Enter `Delete file demo_delete_me.txt`. Inspect the resolved workspace path and impact; approve and confirm; show it was moved to recoverable quarantine rather than permanently erased.
5. **Show resilience.** Force fallback. A supported phrase uses the restricted local fallback. A request like `Call Samarth` is blocked because no phone tool exists.
6. **Show audit.** Open `/health` and `/v1/events`; show the chain status and decision-source/impact/approval/execution events.

## What to claim

- Impact-bound approvals and execution-time revalidation are the key differentiator.
- Gemini interprets tasks into constrained JSON but does not authorize or execute them directly.
- The local fallback is deliberately narrow and fails closed for unknown tasks.
- The demo agent uses HTTP to reach the gateway and has no direct tool executor.

## What not to claim

- Do not claim production deployment, real user authentication, unbounded support for arbitrary natural-language actions, immunity to all prompt injection, or tamper-proof auditing.
- Do not claim email works unless SMTP is configured and a controlled send was verified.
- Do not claim phone calling or arbitrary shell/computer-control is implemented.
