"""Vercel entrypoint. Vercel looks for a module-level ASGI `app` in app.py.

The package lives in src/, so it is added to sys.path here. Configure with
environment variables in the Vercel project (see docs/deployment.md).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from quant_mcp.http_app import create_app

app = create_app()
