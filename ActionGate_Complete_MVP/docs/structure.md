# Repository Structure — Current MVP

```text
ActionGate_Complete_MVP/
├── app/
│   ├── schema.py                 # Strict action schema and allowlists
│   ├── database.py               # Fictional SQLite data and safe query helpers
│   ├── impact.py                 # Database-derived impact and key digest
│   ├── policy.py                 # Deterministic ALLOW/HOLD/BLOCK
│   ├── approval.py               # Scope-bound, expiring, single-use approval
│   ├── execution.py              # Transactional database execution
│   ├── audit.py                  # Hash-chained audit events
│   ├── gemini_client.py          # Standard-library Gemini REST client
│   ├── interpreter.py            # Natural-language database action parser
│   ├── external_tools.py         # Workspace files and optional SMTP email tools
│   ├── gateway_service.py        # Authorization orchestration service
│   ├── gateway_api.py            # Loopback HTTP API enforcement boundary
│   ├── gateway_client.py         # HTTP client used by the demo agent
│   └── streamlit_app.py          # Local reviewer/inspection dashboard
├── scripts/
│   └── demo_agent.py             # Separate agent client; no direct tool access
├── tests/                        # Security, tools, Gemini, and gateway tests
├── data/                          # Generated local database and scoped workspace
├── docs/                          # Concept, architecture, specification and demo
├── setup.ps1                      # Fresh Windows setup and test run
├── start_gateway.ps1               # Starts HTTP gateway
├── start_demo_agent.ps1            # Starts the separate demo agent
├── start_dashboard.ps1             # Starts Streamlit UI
├── run_tests.ps1                   # Compiles and runs tests
├── requirements.txt
└── README.md
```

## Trust boundaries

- The natural-language task and model output are untrusted.
- The model can propose structured JSON only. It does not make the authorization decision.
- The deterministic schema and policy enforce the supported actions.
- Database/file impact is inspected locally, and HOLD actions require a separate demo reviewer label and execution confirmation.
- The demo agent communicates with ActionGate over loopback HTTP and has no direct database, file, email, or shell executor.

## Runtime behavior

The demo database is created on first launch in `data/actiongate_demo.db`. The default file workspace is `data/workspace`, and the delete tool moves one approved file into `.actiongate_trash` rather than permanently erasing it. The bundle intentionally excludes runtime databases, quarantine contents, virtual environments, and credentials.
