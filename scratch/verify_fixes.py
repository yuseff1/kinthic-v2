import sys
sys.path.insert(0, ".")

# Test 1: config shim - AMAC_WEIGHTS must be a list now
from silex_engine.config import AMAC_WEIGHTS, AMAC_THRESHOLD, MAX_CONTEXT_MEMORY_CHARS
print("AMAC_WEIGHTS type:", type(AMAC_WEIGHTS).__name__, "=", AMAC_WEIGHTS)
print("AMAC_THRESHOLD =", AMAC_THRESHOLD)
print("MAX_CONTEXT_MEMORY_CHARS =", MAX_CONTEXT_MEMORY_CHARS)
assert isinstance(AMAC_WEIGHTS, list), "AMAC_WEIGHTS must be list, not dict!"
assert AMAC_THRESHOLD == 0.40, f"AMAC_THRESHOLD should be 0.40, got {AMAC_THRESHOLD}"

# Test 2: ops/service imports
from silex_core.ops.service import (
    install_service, is_service_installed, start_service, stop_service, uninstall_service
)
print("ops.service imports: OK")

# Test 3: daemon.py import string
import pathlib
src = pathlib.Path("scripts/daemon.py").read_text()
assert "silex_core.api.server:app" in src, "WRONG import string still present"
assert '"silex.api.server:app"' not in src, "Old wrong import still present"
print("daemon.py import string: OK")

print()
print("ALL CHECKS PASSED")
