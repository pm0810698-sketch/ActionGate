ActionGate result-status fix

Purpose:
When a reviewer approved a HOLD mutation and execution succeeded, the gateway response used to say outcome=HOLD and message=mutation completed. This made a successful execution look like a still-pending decision.

This patch separates fields:
- authorization_decision: the original policy decision (e.g. HOLD)
- execution_status: SUCCEEDED or FAILED
- outcome: SUCCEEDED or FAILED for the execution result

Files to overwrite from the project root:
- app/gateway_service.py
- tests/test_gateway_service.py

Install:
1. Stop the gateway (Ctrl+C).
2. Extract this ZIP into the ActionGate_Complete_MVP project root, overwriting these two files.
3. Run: .\.venv\Scripts\python.exe -m pytest -q
4. Start the gateway again and run the demo agent.

Verified against the complete bundled project: 45 tests passed.
