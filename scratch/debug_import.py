import sys
from pathlib import Path

print("sys.path is:")
for p in sys.path:
    print("  ", p)

try:
    import silex_core.utils.config as c
    print("silex_core.utils.config file path:", c.__file__)
    print("Available attributes in config:", dir(c))
    print("SILEX_DB:", getattr(c, "SILEX_DB", "NOT FOUND"))
except Exception as e:
    print("Import failed:", e)
