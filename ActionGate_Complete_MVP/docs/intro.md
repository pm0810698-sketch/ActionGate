# ActionGate — Newcomer Introduction

ActionGate is a small local demo showing how an application can check an AI agent's proposed data action before allowing it to run.

## The key rule
AI can help interpret the request, but it cannot grant permission. The gateway validates the action, calculates its impact, applies deterministic policy, and may require a separate reviewer.

## Setup
1. Install Python and VS Code.
2. Create and activate a virtual environment.
3. Install dependencies from `requirements.txt`.
4. Run tests with `python -m pytest`.
5. Start the interface with `python -m streamlit run main.py` once `main.py` is implemented.

## Suggested reading order
1. `idea.md`
2. `specification.md`
3. `architecture.md`
4. `structure.md`
5. `convention.md`
6. `workflow.md`
7. `issues.md`

## Current status
These documents define the intended design. A feature is not complete until code and tests demonstrate it.
