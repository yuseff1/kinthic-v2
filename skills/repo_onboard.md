---
name: repo_onboard
description: First-run repository analysis and architecture knowledge graph bootstrap
metadata:
  trigger: analyze repo onboard architecture knowledge graph first run
inline: true
---

# Repository Onboard Skill

## When to use
Fresh install, new workspace, or user asks to analyze a codebase and build a knowledge graph.

## Workflow

1. List top-level directories and identify entry points (README, pyproject.toml, package.json, etc.).
2. Read key config and main modules — do not dump entire trees.
3. Produce an architecture summary: components, data flow, external dependencies.
4. Register observations into memory with tags `architecture`, `onboarding`.
5. Suggest 3 follow-up tasks (tests, docs, or risky areas to inspect).

## Tone
Technical and concise. Prefer diagrams in mermaid when relationships are non-obvious.
