---
name: daily_briefing
description: Produce a concise morning briefing from goals, memory, and optional web search
metadata:
  trigger: daily briefing morning summary today plan
---

# Daily Briefing Skill

## When to use
User asks for a morning briefing, daily summary, or "what should I focus on today?"

## Workflow

1. Pull active goals from memory/goal tracker context if available.
2. Summarize yesterday's key decisions from recent session turns (last 24h if known).
3. List top 3 priorities for today with rationale.
4. Optionally search for one relevant industry/news headline if user wants external context.
5. End with a single suggested first action (concrete, ≤15 minutes).

## Format
Use short sections: **Priorities**, **Carry-over**, **Suggested first step**. Keep total output under 400 words unless asked for detail.
