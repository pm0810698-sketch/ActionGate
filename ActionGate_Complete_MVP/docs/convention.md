# Code and Style Conventions

- Target Python 3.11+ unless the installed environment requires another supported version.
- Use clear, descriptive names and small functions.
- Use type hints for public functions and data structures.
- Keep security decisions in `policy.py`, not in UI callbacks.
- Keep SQL access in database-related functions; always parameterize values.
- Allowlist table names, column names, operations, and filter operators.
- Never use `eval`, arbitrary SQL from model output, or shell commands derived from user input.
- Treat AI output as untrusted data.
- Fail closed on unknown or malformed actions.
- Do not log secrets or use real personal data.
- Write tests for every security-sensitive change.
- Run `python -m pytest` before considering a change complete.
- Prefer standard-library features unless a dependency clearly helps.
- Add dependencies to `requirements.txt` and explain why they are needed.
- Keep the UI simple and demo-focused until the security core passes tests.
