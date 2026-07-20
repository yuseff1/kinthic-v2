"""Deprecated standalone dashboard API.

This used to run a second, unauthenticated FastAPI app with only a single
`/api/graph` route — duplicating (and colliding on the same port with)
`silex.api.server`, which has since grown the full chat/settings/metrics
surface plus the local API-key + Origin auth gate.

Kept as a thin re-export so `python scripts/dashboard_api.py` (used by
`kinthic web`) still works, but it now serves the exact same authenticated
gateway app as the daemon instead of an insecure duplicate.
"""

import sys
from pathlib import Path

# Dev checkout: agent/ lives at repo root but is not always on sys.path when
# this script is spawned as `python scripts/dashboard_api.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from silex_core.api.server import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn
    from silex_core.utils.config import gateway_host, gateway_port

    uvicorn.run(app, host=gateway_host(), port=gateway_port())
