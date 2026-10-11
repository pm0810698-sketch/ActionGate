"""Root entrypoint for the nested ActionGate project."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent / "ActionGate_Complete_MVP"

if not (PROJECT_ROOT / "app" / "streamlit_app.py").is_file():
    raise RuntimeError("ActionGate application files were not found.")

sys.path.insert(0, str(PROJECT_ROOT))

from app.streamlit_app import main

if __name__ == "__main__":
    main()
