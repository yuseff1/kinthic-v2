"""
Print `gh issue create` commands for items in docs/planning/launch-issue-backlog.md.

Usage (from repo root, after `gh auth login`):

  python scripts/seed_github_issues.py

Pipe to shell only after reviewing commands (labels must exist, e.g. good first issue).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    backlog = root / "docs" / "planning" / "launch-issue-backlog.md"
    if not backlog.exists():
        print(f"Missing {backlog}", file=sys.stderr)
        return 1

    text = backlog.read_text(encoding="utf-8")
    lines = [
        ln.strip() for ln in text.splitlines() if re.match(r"^\d+\.\s+", ln.strip())
    ]
    if not lines:
        print("No numbered lines found in backlog.", file=sys.stderr)
        return 1

    print("# Review then run (repo: openyfai/kinthic)")
    print("# gh label create 'good first issue' --force  # if needed")
    print()
    for ln in lines:
        body = re.sub(r"^\d+\.\s*", "", ln).strip()
        safe = body.replace('"', '\\"')
        print(
            f'gh issue create --title "{safe[:120]}" --body "{safe}" '
            f'--label "good first issue"'
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
