"""
Kinthic Entry Point — starts the cognitive loop.

Usage:
    python -m scripts.run
    or
    python scripts/run.py

All slash-command output is routed through bridge.emit() when the Ink UI is
active so the Ink render tree is never corrupted by Rich.  When Ink is
unavailable the Rich helpers in silex.ui.terminal are used as before.
"""

from __future__ import annotations

# ── LOG SILENCE — must run before any silex import ───────────────────────────
import logging as _logging
import os
from pathlib import Path as _Path

_log_dir = _Path.home() / ".kinthic"
_log_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("KINTHIC_INK_ACTIVE", "1")
_root_log = _logging.getLogger()
if not any(isinstance(h, _logging.FileHandler) for h in _root_log.handlers):
    _root_log.handlers.clear()
    _root_log.setLevel(_logging.DEBUG)
    _fh = _logging.FileHandler(
        str(_log_dir / "kinthic.log"), encoding="utf-8", mode="a"
    )
    _fh.setFormatter(
        _logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    _root_log.addHandler(_fh)
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from silex_core.ui.ink_bridge import KinthicInkBridge
from silex_core.ui.terminal import (
    console,
    get_input,
    show_banner,
    show_startup_summary,
    show_error,
    show_warning,
    show_success,
    show_goals,
    show_help,
    show_memories,
    show_search_results,
    show_sessions,
    show_response,
    show_stats,
    show_graph_stats,
    show_graph_neighborhood,
    show_causal_chain,
    show_contradictions,
    show_hypotheses,
    show_improvements,
    show_uncertainties,
    show_tools,
    show_principles,
    show_proposals,
    show_benchmark_result,
    show_meta_proposal,
)

# ─────────────────────────────────────────────────────────────────────────────
# History file helpers
# ─────────────────────────────────────────────────────────────────────────────

_HISTORY_FILE = _Path.home() / ".kinthic" / "history"
_MAX_HISTORY = 500


def _load_history() -> list[str]:
    try:
        lines = _HISTORY_FILE.read_text(encoding="utf-8").splitlines()
        return [l for l in lines if l.strip()][-_MAX_HISTORY:]
    except Exception:
        return []


def _append_history(entry: str) -> None:
    try:
        _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _HISTORY_FILE.open("a", encoding="utf-8") as fh:
            fh.write(entry.replace("\n", " ") + "\n")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Plain-text formatters — used when Ink bridge is active
# ─────────────────────────────────────────────────────────────────────────────


def _fmt_help() -> str:
    lines = [
        "─── Commands (/ or : prefix) ───",
        "",
        "Memory",
        "  /memories        Show all stored memories",
        "  /search <q>      Search memories by keyword",
        "  /remember <fact> Manually store a memory",
        "  /forget <#>      Delete a memory by index",
        "",
        "Goals",
        "  /goals           Show active goals",
        "  /goal <desc>     Add a new background goal",
        "",
        "World Model",
        "  /graph           Show knowledge graph stats",
        "  /graph <concept> Show neighborhood of a concept",
        "  /why <A> -> <B>  Find causal chain from A to B",
        "  /contradictions  Show unresolved contradictions",
        "  /hypotheses      Show pending predictions",
        "  /hypo-confirm <id>  Mark hypothesis confirmed",
        "  /hypo-deny <id>     Mark hypothesis denied",
        "",
        "Cognitive",
        "  /improvements    Show recent self-corrections",
        "  /uncertainties   Show known knowledge gaps",
        "  /tools           Show registered tools",
        "  /principles      Show discovered universal laws",
        "  /benchmark       Run the benchmark suite",
        "  /meta            Trigger meta-reasoning analysis",
        "",
        "Proposals",
        "  /proposals       Show improvement proposals",
        "  /prop-approve <uuid>  Approve a proposal",
        "  /prop-reject <uuid>   Reject a proposal",
        "",
        "Session",
        "  /stats           Show session statistics",
        "  /sessions        List all past sessions",
        "  /export          Export session to JSON",
        "",
        "Routing",
        "  /model [name]    Show/switch LLM provider",
        "  /mode <mode>     Set routing (speed|quality|auto)",
        "  /providers       List all providers",
        "",
        "RAG",
        "  /index [path]    Index folder into vector DB",
        "  /rag <query>     Search file index directly",
        "",
        "Plugins",
        "  /plugins         List all registered tools",
        "  /plugin reload   Hot-reload user plugins",
        "",
        "Voice",
        "  /voice [on|off]  Toggle voice input",
        "",
        "System",
        "  /clear           Clear the screen",
        "  /quit            Exit Kinthic",
        "",
        "Press Esc to cancel a running turn.",
    ]
    return "\n".join(lines)


def _fmt_memories(memories: list) -> str:
    if not memories:
        return "No memories stored yet."
    lines = [f"Memories ({len(memories)} total)", ""]
    for i, m in enumerate(memories, 1):
        imp_bar = "█" * int(m.importance * 5)
        imp_bar = imp_bar.ljust(5, "░")
        tags = ", ".join(m.tags[:3]) if m.tags else "—"
        source = m.source.value if hasattr(m.source, "value") else str(m.source)
        lines.append(f"  {i:2}. [{imp_bar}] {m.content[:60]}  ({source}) [{tags}]")
    lines.append("")
    lines.append("Use /forget <#> to remove a memory.")
    return "\n".join(lines)


def _fmt_goals(goals: list) -> str:
    if not goals:
        return "No goals tracked yet."
    lines = [f"Goals ({len(goals)} total)", ""]
    for i, g in enumerate(goals, 1):
        p_val = g.priority.value if hasattr(g.priority, "value") else str(g.priority)
        s_val = g.status.value if hasattr(g.status, "value") else str(g.status)
        notes = f"  [{g.completion_notes[:30]}]" if g.completion_notes else ""
        lines.append(
            f"  {i:2}. [{p_val.upper():8}] [{s_val:10}] {g.description[:55]}{notes}"
        )
    return "\n".join(lines)


def _fmt_stats(info: dict) -> str:
    lines = [
        "Session Statistics",
        "",
        f"  Session ID      : {info.get('session_id', 'unknown')}",
        f"  Turns (session) : {info.get('turn_count', 0)}",
        f"  Turns (all time): {info.get('total_turns', 0)}",
        f"  Total memories  : {info.get('total_memories', 0)}",
        f"  Knowledge nodes : {info.get('graph_nodes', 0)}",
        f"  Causal edges    : {info.get('graph_edges', 0)}",
        f"  Active goals    : {info.get('active_goals', 0)}",
        f"  Mem (session)   : {info.get('memories_this_session', 0)}",
        f"  Avg confidence  : {info.get('avg_confidence', 0):.0%}",
    ]
    return "\n".join(lines)


def _fmt_sessions(sessions: list) -> str:
    if not sessions:
        return "No past sessions."
    lines = [f"Session History ({len(sessions)} sessions)", ""]
    for i, s in enumerate(sessions, 1):
        started = s.started_at[:19].replace("T", " ") if s.started_at else "?"
        conf = f"{s.avg_confidence:.0%}" if s.avg_confidence > 0 else "—"
        lines.append(
            f"  {i:2}. {s.id[:8]}  {started}  "
            f"{s.turn_count} turns  {s.memories_created} memories  {conf}"
        )
    return "\n".join(lines)


def _fmt_search(memories: list, query: str) -> str:
    if not memories:
        return f"No memories matching '{query}'."
    lines = [f"Search results for '{query}' ({len(memories)} found)", ""]
    for i, m in enumerate(memories, 1):
        imp_bar = "█" * int(m.importance * 5)
        imp_bar = imp_bar.ljust(5, "░")
        source = m.source.value if hasattr(m.source, "value") else str(m.source)
        lines.append(f"  {i:2}. [{imp_bar}] {m.content[:65]}  ({source})")
    return "\n".join(lines)


def _fmt_graph_stats(stats: dict) -> str:
    if not stats:
        return "Knowledge graph is empty. Talk to Kinthic to build it."
    lines = [
        "Knowledge Graph",
        "",
        f"  Nodes : {stats.get('node_count', 0)}",
        f"  Edges : {stats.get('edge_count', 0)}",
        f"  Types : {', '.join(stats.get('node_types', []))[:80]}",
    ]
    top = stats.get("top_nodes", [])
    if top:
        lines.append("")
        lines.append("  Top concepts:")
        for n in top[:10]:
            lines.append(f"    {n['label'][:40]}  ({n['degree']} connections)")
    return "\n".join(lines)


def _fmt_graph_neighborhood(data: dict) -> str:
    if not data:
        return "Concept not found in knowledge graph."
    lines = [f"Neighborhood: {data.get('center', '?')}", ""]
    for edge in data.get("edges", [])[:20]:
        lines.append(
            f"  {edge.get('from', '?')[:30]}  —[{edge.get('relation', '?')}]→  {edge.get('to', '?')[:30]}"
        )
    return "\n".join(lines)


def _fmt_causal_chain(chain: list, from_c: str, to_c: str) -> str:
    if not chain:
        return f"No causal chain found from '{from_c}' to '{to_c}'."
    lines = [f"Causal chain: {from_c} → {to_c}", ""]
    for step in chain:
        if isinstance(step, dict):
            lines.append(
                f"  {step.get('from', '?')[:30]}  ──[{step.get('relation', '?')}]──▶  {step.get('to', '?')[:30]}"
            )
        else:
            lines.append(f"  {step}")
    return "\n".join(lines)


def _fmt_contradictions(items: list) -> str:
    if not items:
        return "No contradictions detected. Knowledge graph is consistent."
    lines = [f"Contradictions ({len(items)} total)", ""]
    for c in items[:20]:
        if isinstance(c, dict):
            lines.append(
                f"  • {c.get('claim_a', '?')[:50]}  ⟺  {c.get('claim_b', '?')[:50]}"
                + (
                    f"\n    [{c.get('status', 'open')}] {c.get('resolution', '')[:60]}"
                    if c.get("resolution")
                    else ""
                )
            )
        else:
            lines.append(f"  • {str(c)[:100]}")
    return "\n".join(lines)


def _fmt_hypotheses(items: list) -> str:
    if not items:
        return "No pending hypotheses."
    lines = [f"Hypotheses ({len(items)} total)", ""]
    for h in items[:20]:
        if isinstance(h, dict):
            conf = f"{h.get('confidence', 0):.0%}"
            lines.append(
                f"  [{h.get('status', 'pending'):8}] [{conf}] {h.get('statement', '?')[:70]}"
                + f"\n    id: {h.get('id', '?')[:36]}"
            )
        else:
            lines.append(f"  • {str(h)[:100]}")
    return "\n".join(lines)


def _fmt_improvements(items: list) -> str:
    if not items:
        return "No self-improvements recorded yet."
    lines = [f"Recent improvements ({len(items)} total)", ""]
    for imp in items[:20]:
        if isinstance(imp, dict):
            lines.append(
                f"  [{imp.get('trigger', '?')[:20]}]  {imp.get('description', '?')[:70]}"
            )
        else:
            lines.append(f"  • {str(imp)[:100]}")
    return "\n".join(lines)



def _fmt_uncertainties(items: list) -> str:
    if not items:
        return "No uncertainty flags recorded."
    lines = [f"Uncertainty flags ({len(items)} total)", ""]
    for u in items[:20]:
        if isinstance(u, dict):
            lines.append(f"  [{u.get('flag', '?')}] {u.get('description', '?')[:80]}")
        else:
            lines.append(f"  • {str(u)[:100]}")
    return "\n".join(lines)


def _fmt_tools(registry) -> str:
    if not registry or not hasattr(registry, "tools"):
        return "No tools registered."
    lines = [f"Registered tools ({len(registry.tools)} total)", ""]
    for name, tool in registry.tools.items():
        desc = (tool.description or "")[:60]
        lines.append(f"  • {name}: {desc}")
    return "\n".join(lines)


def _fmt_principles(items: list) -> str:
    if not items:
        return "No universal principles discovered yet."
    lines = [f"Principles ({len(items)} total)", ""]
    for p in items[:20]:
        if isinstance(p, dict):
            lines.append(
                f"  [{p.get('category', '?')[:15]}] {p.get('principle', '?')[:80]}"
            )
        else:
            lines.append(f"  • {str(p)[:100]}")
    return "\n".join(lines)


def _fmt_proposals(items: list) -> str:
    if not items:
        return "No improvement proposals pending."
    lines = [f"Proposals ({len(items)} total)", ""]
    for prop in items[:20]:
        if isinstance(prop, dict):
            lines.append(
                f"  [{prop.get('status', '?'):10}] {prop.get('title', '?')[:60]}"
                + f"\n    id: {str(prop.get('id', '?'))[:36]}"
                + (
                    f"\n    {prop.get('summary', '')[:80]}"
                    if prop.get("summary")
                    else ""
                )
            )
        else:
            lines.append(f"  • {str(prop)[:100]}")
    return "\n".join(lines)


def _fmt_benchmark(result) -> str:
    if not result:
        return "Benchmark produced no result."
    if isinstance(result, dict):
        lines = [
            "Benchmark Results",
            "",
            f"  Overall score : {result.get('score', 0):.1f} / {result.get('max_score', 100):.1f}",
            f"  Pass rate     : {result.get('pass_rate', 0):.0%}",
            "",
        ]
        for cat, score in result.get("category_scores", {}).items():
            lines.append(f"  {cat:<25}: {score:.1f}")
        failures = result.get("failures", [])
        if failures:
            lines.append("")
            lines.append(f"  Failures ({len(failures)}):")
            for f in failures[:5]:
                lines.append(f"    • {f}")
        return "\n".join(lines)
    return str(result)[:400]


def _fmt_meta_proposal(prop) -> str:
    if not prop:
        return "Meta-reasoning produced no proposal."
    if isinstance(prop, dict):
        lines = [
            "Meta-Reasoning Analysis",
            "",
            f"  Finding  : {prop.get('finding', '?')[:80]}",
            f"  Proposal : {prop.get('title', '?')[:80]}",
            f"  Priority : {prop.get('priority', '?')}",
        ]
        if prop.get("id"):
            lines.append(f"  ID       : {str(prop['id'])[:36]}")
        lines += [
            "",
            "Use /prop-approve <id> or /prop-reject <id> to act on this proposal.",
        ]
        return "\n".join(lines)
    return str(prop)[:400]


# ─────────────────────────────────────────────────────────────────────────────
# Main async run loop
# ─────────────────────────────────────────────────────────────────────────────


async def _ink_approval_listener(
    bridge: KinthicInkBridge,
    tool_registry,
    turn_emitter_holder: list,
) -> None:
    """Forward Ink approval_response packets to the tool approval gate."""
    import logging

    log = logging.getLogger("kinthic.approval")

    while bridge.is_active:
        packet = await bridge.read_approval_response(timeout=3600.0)
        if packet is None:
            continue

        params = packet.get("params") or {}
        approval_id = params.get("id")
        if not approval_id:
            continue

        approved = bool(params.get("approved"))
        status = "approved" if approved else "rejected"

        tool_name = "tool"
        risk_level = "unknown"
        if tool_registry.db:
            try:
                row = await tool_registry.db.fetch_one(
                    "SELECT tool_name, risk_level FROM tool_approvals WHERE id = ?",
                    (approval_id,),
                )
                if row:
                    tool_name = row["tool_name"] or tool_name
                    risk_level = row["risk_level"] or risk_level
            except Exception:
                pass

        turn_emitter = turn_emitter_holder[0] if turn_emitter_holder else None
        if turn_emitter is not None:
            await turn_emitter.approval_result(
                approval_id,
                tool_name,
                risk_level,
                approved,
            )
            if approved:
                await turn_emitter.tool_progress(tool_name, "Running approved tool...")

        try:
            ok = await tool_registry.resolve_approval(approval_id, status)
            if not ok:
                log.warning("Ink approval resolve failed for id=%s", approval_id)
        except Exception:
            log.exception("Ink approval resolve error for id=%s", approval_id)


async def run() -> None:
    """Main async entry point."""
    from silex_core.harness.wrapper import LoopWrapper
    loop = LoopWrapper()
    bridge = KinthicInkBridge()

    # History
    session_history: list[str] = _load_history()

    # Cancellation handle — updated on every cognitive turn
    _current_process_task: asyncio.Task | None = None
    approval_task: asyncio.Task | None = None
    _turn_emitter_holder: list = [None]

    try:
        await bridge.start()

        if not bridge.is_active:
            os.environ.pop("KINTHIC_INK_ACTIVE", None)
            import logging as _lg

            _root = _lg.getLogger()
            if not any(not isinstance(h, _lg.FileHandler) for h in _root.handlers):
                from rich.logging import RichHandler as _RH

                _rh = _RH(
                    rich_tracebacks=True,
                    show_time=True,
                    show_path=False,
                    markup=True,
                    tracebacks_show_locals=False,
                )
                _rh.setFormatter(_lg.Formatter("%(message)s"))
                _root.addHandler(_rh)
            show_banner()
            show_warning(
                "Kinthic is running in Rich fallback mode, not the production Ink TUI.\n"
                f"Reason: {bridge.fallback_reason}\n"
                "Fix: run `cd kinthic-ink-ui && npm install && npm run build`, then restart."
            )

        await loop.startup()

        if bridge.is_active:
            approval_task = asyncio.create_task(
                _ink_approval_listener(
                    bridge, loop.tool_registry, _turn_emitter_holder
                ),
                name="kinthic-ink-approval",
            )

        # Emit history to Ink for up/down arrow navigation
        if bridge.is_active and session_history:
            await bridge.emit(
                {
                    "type": "history_update",
                    "data": {"history": session_history[-200:]},
                }
            )

        # WSL2 cross-OS mount performance boundary warning
        cwd_str = str(Path.cwd())
        if cwd_str.startswith("/mnt/"):
            warning_msg = (
                "⚠ WSL2 Filesystem Boundary Warning:\n"
                "  Your workspace is under /mnt/ — operations will be slow.\n"
                "  For best performance, clone inside the native WSL2 filesystem."
            )
            if bridge.is_active:
                await bridge.emit({"type": "response", "data": {"text": warning_msg}})
            else:
                show_warning(warning_msg)

        info = await loop.get_session_info()
        if not bridge.is_active:
            sessions = await loop.get_all_sessions()
            show_startup_summary(
                memory_count=info["total_memories"],
                goal_count=info["active_goals"],
                session_count=len(sessions),
                total_turns=info["total_turns"],
            )
        if not bridge.is_active and info.get("graph_nodes", 0) > 0:
            console.print(
                f"  [bright_cyan]◆[/] [dim]World model:[/] "
                f"[bright_cyan]{info['graph_nodes']} nodes[/][dim],[/] "
                f"[bright_cyan]{info['graph_edges']} edges[/]"
            )
            console.print()

        _voice_session = None
        while True:
            if _voice_session and _voice_session._active:
                if bridge.is_active:
                    await bridge.emit(
                        {"type": "thinking", "data": {"status": "🎤 Listening..."}}
                    )
                else:
                    console.print("\n  [bold bright_cyan]🎤 Listening...[/]")
                try:
                    user_input = await asyncio.to_thread(
                        _voice_session._listener.listen
                    )
                except Exception as exc:
                    msg = f"Voice listening failed: {exc}"
                    if bridge.is_active:
                        await bridge.emit_error(msg)
                    else:
                        show_error(msg)
                    _voice_session.stop()
                    _voice_session = None
                    continue

                if not user_input or not user_input.strip():
                    continue

                if bridge.is_active:
                    await bridge.emit(
                        {
                            "type": "response",
                            "data": {"text": f'🎤 Heard: "{user_input}"'},
                        }
                    )
                else:
                    console.print(f"  [bold bright_white]Heard ›[/] {user_input}")

                lower_input = user_input.lower().strip().rstrip(".")
                if lower_input in (
                    "voice off",
                    "turn off voice",
                    "disable voice",
                    "stop voice",
                    "/voice off",
                ):
                    user_input = "/voice off"
                elif lower_input.startswith("slash "):
                    user_input = "/" + user_input[6:]
                elif lower_input.startswith("colon "):
                    user_input = ":" + user_input[6:]
            else:
                if bridge.is_active:
                    user_input = await bridge.read_user_input()
                    if user_input is None:
                        break
                else:
                    user_input = get_input()

            if not user_input:
                continue

            # ── Command dispatch ─────────────────────────────────────────────
            if user_input.startswith("/") or user_input.startswith(":"):
                if user_input.startswith("/"):
                    user_input = ":" + user_input[1:]
                cmd_parts = user_input.split(maxsplit=1)
                cmd = cmd_parts[0].lower().strip()
                cmd_arg = cmd_parts[1].strip() if len(cmd_parts) > 1 else ""

                # ── Helpers for DRY command responses ────────────────────────
                async def _emit_or(text: str, show_fn=None, *args) -> None:  # noqa: E731
                    if bridge.is_active:
                        await bridge.emit({"type": "response", "data": {"text": text}})
                    elif show_fn:
                        show_fn(*args)
                    else:
                        console.print(text)

                # ── Quit ─────────────────────────────────────────────────────
                if cmd in (":quit", ":exit", ":q"):
                    msg = "Kinthic signing off. Memories persisted."
                    if bridge.is_active:
                        await bridge.emit({"type": "response", "data": {"text": msg}})
                    else:
                        console.print(f"\n  [dim]{msg}[/]\n")
                    break

                # ── Help ─────────────────────────────────────────────────────
                elif cmd in (":help", ":h"):
                    if bridge.is_active:
                        await bridge.emit(
                            {"type": "response", "data": {"text": _fmt_help()}}
                        )
                    else:
                        show_help()
                    continue

                # ── Memories ─────────────────────────────────────────────────
                elif cmd in (":memories", ":mem"):
                    memories = await loop.get_all_memories()
                    if bridge.is_active:
                        await bridge.emit(
                            {
                                "type": "response",
                                "data": {"text": _fmt_memories(memories)},
                            }
                        )
                    else:
                        show_memories(memories)
                    continue

                # ── Goals ────────────────────────────────────────────────────
                elif cmd in (":goals", ":g"):
                    goals = await loop.get_all_goals()
                    if bridge.is_active:
                        await bridge.emit(
                            {"type": "response", "data": {"text": _fmt_goals(goals)}}
                        )
                    else:
                        show_goals(goals)
                    continue

                # ── Goal (add new) ───────────────────────────────────────────
                elif cmd in (":goal",):
                    if not cmd_arg:
                        msg = "Usage: /goal <description>"
                        await _emit_or(msg, show_warning, msg)
                        continue
                    try:
                        new_goal = await loop.create_goal(cmd_arg)
                        goal_id = getattr(new_goal, "id", "?")
                        msg = f'Goal created: "{cmd_arg[:60]}" (id: {str(goal_id)[:8]})'
                    except Exception as exc:
                        msg = f"Failed to create goal: {exc}"
                    await _emit_or(
                        msg,
                        show_success if "created" in msg.lower() else show_error,
                        msg,
                    )
                    continue

                # ── Stats ────────────────────────────────────────────────────
                elif cmd in (":stats", ":s"):
                    stats = await loop.get_session_info()
                    if bridge.is_active:
                        await bridge.emit(
                            {"type": "response", "data": {"text": _fmt_stats(stats)}}
                        )
                    else:
                        show_stats(stats)
                    continue

                # ── Sessions ─────────────────────────────────────────────────
                elif cmd in (":sessions", ":sess"):
                    sessions = await loop.get_all_sessions()
                    if bridge.is_active:
                        await bridge.emit(
                            {
                                "type": "response",
                                "data": {"text": _fmt_sessions(sessions)},
                            }
                        )
                    else:
                        show_sessions(sessions)
                    continue

                # ── Search ───────────────────────────────────────────────────
                elif cmd in (":search",):
                    if not cmd_arg:
                        msg = "Usage: /search <query>"
                        await _emit_or(msg, show_warning, msg)
                        continue
                    results = await loop.search_memories(cmd_arg)
                    if bridge.is_active:
                        await bridge.emit(
                            {
                                "type": "response",
                                "data": {"text": _fmt_search(results, cmd_arg)},
                            }
                        )
                    else:
                        show_search_results(results, cmd_arg)
                    continue

                # ── Remember ─────────────────────────────────────────────────
                elif cmd in (":remember", ":rem"):
                    if not cmd_arg:
                        msg = "Usage: /remember <fact to store>"
                        await _emit_or(msg, show_warning, msg)
                        continue
                    memory = await loop.add_manual_memory(cmd_arg)
                    if memory is None:
                        msg = "Blocked: this content was rejected by the memory integrity guard."
                        await _emit_or(msg, show_warning, msg)
                        continue
                    msg = f'Stored: "{memory.content[:50]}"'
                    await _emit_or(msg, show_success, msg)
                    continue

                # ── Forget ───────────────────────────────────────────────────
                elif cmd in (":forget",):
                    if not cmd_arg:
                        msg = "Usage: /forget <memory number>"
                        await _emit_or(msg, show_warning, msg)
                        continue
                    try:
                        index = int(cmd_arg)
                        deleted = await loop.forget_memory(index)
                        if deleted:
                            msg = f"Memory #{index} deleted."
                            await _emit_or(msg, show_success, msg)
                        else:
                            msg = f"Memory #{index} not found."
                            await _emit_or(msg, show_error, msg)
                    except ValueError:
                        msg = "Provide a number, e.g. /forget 3"
                        await _emit_or(msg, show_error, msg)
                    continue

                # ── Graph ─────────────────────────────────────────────────────
                elif cmd in (":graph",):
                    if cmd_arg:
                        data = await loop.get_graph_neighborhood(cmd_arg)
                        if data:
                            if bridge.is_active:
                                await bridge.emit(
                                    {
                                        "type": "response",
                                        "data": {"text": _fmt_graph_neighborhood(data)},
                                    }
                                )
                            else:
                                show_graph_neighborhood(data)
                        else:
                            msg = f"'{cmd_arg}' not found in the knowledge graph."
                            await _emit_or(msg, show_warning, msg)
                    else:
                        stats = await loop.get_graph_stats()
                        if bridge.is_active:
                            await bridge.emit(
                                {
                                    "type": "response",
                                    "data": {"text": _fmt_graph_stats(stats)},
                                }
                            )
                        else:
                            show_graph_stats(stats)
                    continue

                # ── Why ───────────────────────────────────────────────────────
                elif cmd in (":why",):
                    if not cmd_arg or "->" not in cmd_arg:
                        msg = "Usage: /why <concept A> -> <concept B>"
                        await _emit_or(msg, show_warning, msg)
                        continue
                    parts = cmd_arg.split("->", 1)
                    from_c = parts[0].strip()
                    to_c = parts[1].strip()
                    chain = await loop.get_causal_chain(from_c, to_c)
                    if bridge.is_active:
                        await bridge.emit(
                            {
                                "type": "response",
                                "data": {
                                    "text": _fmt_causal_chain(chain or [], from_c, to_c)
                                },
                            }
                        )
                    else:
                        show_causal_chain(chain or [], from_c, to_c)
                    continue

                # ── Contradictions ────────────────────────────────────────────
                elif cmd in (":contradictions", ":contra"):
                    contras = await loop.get_contradictions()
                    if bridge.is_active:
                        await bridge.emit(
                            {
                                "type": "response",
                                "data": {"text": _fmt_contradictions(contras)},
                            }
                        )
                    else:
                        show_contradictions(contras)
                    continue

                # ── Hypotheses ────────────────────────────────────────────────
                elif cmd in (":hypotheses", ":hypo"):
                    hypos = await loop.get_hypotheses()
                    if bridge.is_active:
                        await bridge.emit(
                            {
                                "type": "response",
                                "data": {"text": _fmt_hypotheses(hypos)},
                            }
                        )
                    else:
                        show_hypotheses(hypos)
                    continue

                elif cmd in (":hypo-confirm", ":hypc"):
                    if not cmd_arg:
                        msg = "Usage: /hypo-confirm <hypothesis-uuid>"
                        await _emit_or(msg, show_warning, msg)
                        continue
                    ok = await loop.resolve_hypothesis(cmd_arg, "confirm")
                    if ok:
                        msg = f"Hypothesis {cmd_arg.strip()[:8]}… marked confirmed."
                        await _emit_or(msg, show_success, msg)
                    else:
                        msg = "Hypothesis not found or not pending."
                        await _emit_or(msg, show_error, msg)
                    continue

                elif cmd in (":hypo-deny", ":hypd"):
                    if not cmd_arg:
                        msg = "Usage: /hypo-deny <hypothesis-uuid>"
                        await _emit_or(msg, show_warning, msg)
                        continue
                    ok = await loop.resolve_hypothesis(cmd_arg, "deny")
                    if ok:
                        msg = f"Hypothesis {cmd_arg.strip()[:8]}… marked denied."
                        await _emit_or(msg, show_success, msg)
                    else:
                        msg = "Hypothesis not found or not pending."
                        await _emit_or(msg, show_error, msg)
                    continue

                # ── Export ────────────────────────────────────────────────────
                elif cmd in (":export",):
                    filepath = await loop.export_session()
                    if filepath:
                        msg = f"Session exported to: {filepath}"
                        await _emit_or(msg, show_success, msg)
                    else:
                        msg = "Nothing to export yet."
                        await _emit_or(msg, show_error, msg)
                    continue

                # ── Improvements ──────────────────────────────────────────────
                elif cmd in (":improvements", ":imp"):
                    improvements = await loop.get_recent_improvements()
                    if bridge.is_active:
                        await bridge.emit(
                            {
                                "type": "response",
                                "data": {"text": _fmt_improvements(improvements)},
                            }
                        )
                    else:
                        show_improvements(improvements)
                    continue

                # ── Uncertainties ─────────────────────────────────────────────
                elif cmd in (":uncertainties", ":unc"):
                    uncertainties = await loop.get_uncertainties()
                    if bridge.is_active:
                        await bridge.emit(
                            {
                                "type": "response",
                                "data": {"text": _fmt_uncertainties(uncertainties)},
                            }
                        )
                    else:
                        show_uncertainties(uncertainties)
                    continue

                # ── Tools ─────────────────────────────────────────────────────
                elif cmd in (":tools",):
                    if bridge.is_active:
                        await bridge.emit(
                            {
                                "type": "response",
                                "data": {"text": _fmt_tools(loop.tool_registry)},
                            }
                        )
                    else:
                        show_tools(loop.tool_registry)
                    continue

                # ── Principles ────────────────────────────────────────────────
                elif cmd in (":principles", ":prin"):
                    principles = await loop.get_principles()
                    if bridge.is_active:
                        await bridge.emit(
                            {
                                "type": "response",
                                "data": {"text": _fmt_principles(principles)},
                            }
                        )
                    else:
                        show_principles(principles)
                    continue

                # ── Proposals ────────────────────────────────────────────────
                elif cmd in (":proposals", ":prop"):
                    proposals = await loop.get_proposals()
                    if bridge.is_active:
                        await bridge.emit(
                            {
                                "type": "response",
                                "data": {"text": _fmt_proposals(proposals)},
                            }
                        )
                    else:
                        show_proposals(proposals)
                    continue

                elif cmd in (":prop-approve",):
                    if not cmd_arg:
                        msg = "Usage: /prop-approve <proposal-uuid>"
                        await _emit_or(msg, show_warning, msg)
                        continue
                    ok = await loop.resolve_improvement_proposal(
                        cmd_arg.strip(), "approved"
                    )
                    if ok:
                        msg = "Proposal marked approved."
                        await _emit_or(msg, show_success, msg)
                    else:
                        msg = "Proposal not found or invalid status."
                        await _emit_or(msg, show_error, msg)
                    continue

                elif cmd in (":prop-reject",):
                    if not cmd_arg:
                        msg = "Usage: /prop-reject <proposal-uuid>"
                        await _emit_or(msg, show_warning, msg)
                        continue
                    ok = await loop.resolve_improvement_proposal(
                        cmd_arg.strip(), "rejected"
                    )
                    if ok:
                        msg = "Proposal marked rejected."
                        await _emit_or(msg, show_success, msg)
                    else:
                        msg = "Proposal not found or invalid status."
                        await _emit_or(msg, show_error, msg)
                    continue

                # ── Benchmark ─────────────────────────────────────────────────
                elif cmd in (":benchmark", ":bench"):
                    try:
                        if bridge.is_active:
                            await bridge.emit(
                                {
                                    "type": "thinking",
                                    "data": {"status": "Running benchmark suite..."},
                                }
                            )
                            result = await loop.run_benchmark()
                            await bridge.emit(
                                {
                                    "type": "response",
                                    "data": {"text": _fmt_benchmark(result)},
                                }
                            )
                        else:
                            console.print(
                                "\n  [bright_magenta]Running benchmark suite (this will take a while)...[/]\n"
                            )
                            with console.status(
                                "[bright_magenta]  Benchmarking...", spinner="dots"
                            ) as status:
                                result = await loop.run_benchmark(
                                    status_callback=status.update
                                )
                            show_benchmark_result(result)
                    except Exception as exc:
                        await _emit_or(str(exc), show_error, str(exc))
                    continue

                # ── Meta ──────────────────────────────────────────────────────
                elif cmd in (":meta",):
                    try:
                        if bridge.is_active:
                            await bridge.emit(
                                {
                                    "type": "thinking",
                                    "data": {
                                        "status": "Running meta-reasoning analysis..."
                                    },
                                }
                            )
                            proposal = await loop.run_meta_analysis()
                            await bridge.emit(
                                {
                                    "type": "response",
                                    "data": {"text": _fmt_meta_proposal(proposal)},
                                }
                            )
                        else:
                            console.print(
                                "\n  [bright_magenta]Running meta-reasoning analysis...[/]\n"
                            )
                            with console.status(
                                "[bright_magenta]  Analyzing...", spinner="dots"
                            ) as status:
                                proposal = await loop.run_meta_analysis(
                                    status_callback=status.update
                                )
                            show_meta_proposal(proposal)
                    except Exception as exc:
                        await _emit_or(str(exc), show_error, str(exc))
                    continue

                # ── Model ─────────────────────────────────────────────────────
                elif cmd in (":model",):
                    if not cmd_arg:
                        available = loop.smart_router.list_available()
                        lines = ["Active providers:\n"]
                        for p in available:
                            status_str = (
                                "✓ active"
                                if p["active"]
                                else ("✓ ready" if p["available"] else "✗ no key")
                            )
                            lines.append(f"  [{status_str}] {p['label']} ({p['name']})")
                            lines.append(
                                f"         fast: {p['fast_model']} | reasoning: {p['reasoning_model']}"
                            )
                        await _emit_or("\n".join(lines))
                    else:
                        ok = loop.smart_router.set_provider(cmd_arg.strip())
                        loop.llm = loop.smart_router.get_proxy()
                        msg = (
                            f"Switched to provider: {cmd_arg}"
                            if ok
                            else f"Provider '{cmd_arg}' unavailable — check API key."
                        )
                        if bridge.is_active:
                            await bridge.emit(
                                {"type": "response", "data": {"text": msg}}
                            )
                        else:
                            (show_success if ok else show_error)(msg)
                    continue

                # ── Mode ──────────────────────────────────────────────────────
                elif cmd in (":mode",):
                    valid_modes = {"auto", "speed", "quality", "local"}
                    mode = cmd_arg.strip().lower()
                    if mode not in valid_modes:
                        msg = f"Invalid mode. Choose: {', '.join(valid_modes)}"
                        await _emit_or(msg, show_error, msg)
                    else:
                        loop.smart_router.set_mode(mode)
                        msg = f"Routing mode set to: {mode}"
                        await _emit_or(msg, show_success, msg)
                    continue

                # ── Providers ────────────────────────────────────────────────
                elif cmd in (":providers",):
                    available = loop.smart_router.list_available()
                    lines = ["Available LLM providers:\n"]
                    for p in available:
                        status_str = (
                            "● ACTIVE"
                            if p["active"]
                            else ("○ ready" if p["available"] else "✗ no key")
                        )
                        lines.append(
                            f"  {status_str}  {p['label']} — use: /model {p['name']}"
                        )
                    await _emit_or("\n".join(lines))
                    continue

                # ── Index ─────────────────────────────────────────────────────
                elif cmd in (":index",):
                    from silex_core.utils.config import WORKSPACE_DIR

                    folder = cmd_arg.strip() or str(WORKSPACE_DIR)
                    if folder == "--clear":
                        loop.file_indexer.clear()
                        msg = "File index cleared."
                    else:
                        from pathlib import Path as _P

                        target = _P(folder).resolve()
                        if not target.is_dir():
                            msg = f"Not a directory: {folder}"
                        else:
                            if bridge.is_active:
                                await bridge.emit(
                                    {
                                        "type": "thinking",
                                        "data": {"status": f"Indexing {folder}..."},
                                    }
                                )
                            else:
                                console.print(
                                    f"  [bright_magenta]Indexing {folder}...[/]"
                                )
                            stats = await asyncio.to_thread(
                                loop.file_indexer.index_folder, target
                            )
                            msg = f"Indexed {stats['indexed']} files ({stats['skipped']} unchanged, {stats['errors']} errors)"
                    await _emit_or(msg, show_success, msg)
                    continue

                # ── RAG ───────────────────────────────────────────────────────
                elif cmd in (":rag",):
                    if not cmd_arg:
                        msg = "Usage: /rag <query>"
                        await _emit_or(msg, show_warning, msg)
                        continue
                    results = loop.file_indexer.search(cmd_arg, n_results=5)
                    if not results:
                        msg = "No results found in file index. Run /index first."
                    else:
                        lines = [f"Found {len(results)} results:\n"]
                        for r in results:
                            lines.append(f"  {r['path']}:{r['start_line']}")
                            lines.append(f"  {r['content'][:200]}\n")
                        msg = "\n".join(lines)
                    await _emit_or(msg)
                    continue

                # ── Plugins ───────────────────────────────────────────────────
                elif cmd in (":plugins",):
                    from silex_core.plugins.loader import list_loaded_plugins

                    plugin_tool_names = {p["tool_name"] for p in list_loaded_plugins()}
                    lines = ["Registered tools:\n"]
                    for name, tool in loop.tool_registry.tools.items():
                        tag = " [plugin]" if name in plugin_tool_names else ""
                        desc = (tool.description or "")[:60]
                        lines.append(f"  • {name}{tag}: {desc}")
                    plugin_count = len(plugin_tool_names)
                    builtin_count = len(loop.tool_registry.tools) - plugin_count
                    lines.append(
                        f"\n  {builtin_count} built-in tools, "
                        f"{plugin_count} user plugin(s). "
                        f"Drop folders into ~/.kinthic/plugins/tools/ to add more."
                    )
                    await _emit_or("\n".join(lines))
                    continue

                elif cmd in (":plugin",) and cmd_arg.strip() == "reload":
                    try:
                        loop.tool_registry._register_defaults()
                        if hasattr(loop, "skill_loader") and loop.skill_loader:
                            loop.tool_registry.register_skill_tools(loop.skill_loader)
                            loop.skill_loader.load_all()
                            skill_count = len(loop.skill_loader.skills)
                        else:
                            skill_count = 0
                        mcp_count = await loop.tool_registry.reload_mcp_tools()
                        from silex_core.plugins.loader import list_loaded_plugins

                        user_plugins = list_loaded_plugins()
                        msg = (
                            f"Reloaded: {len(user_plugins)} tool plugin(s), "
                            f"{skill_count} skill(s), {mcp_count} MCP tool(s) active."
                        )
                    except Exception as exc:
                        msg = f"Plugin reload error: {exc}"
                    await _emit_or(msg, show_success, msg)
                    continue

                elif cmd in (":plugin",) and cmd_arg.strip().startswith("search"):
                    query = cmd_arg.strip()[len("search") :].strip()
                    try:
                        from silex_core.plugins.registry import get_registry

                        reg = get_registry()
                        results = reg.search(query) if query else reg.get_all()
                        if not results:
                            msg = f"No plugins found matching '{query}'."
                        else:
                            msg = (
                                f"KinthicHub — {len(results)} result(s):\n\n"
                                + reg.format_list(results)
                            )
                    except Exception as exc:
                        msg = f"Registry search error: {exc}"
                    await _emit_or(msg)
                    continue

                elif cmd in (":plugin",) and cmd_arg.strip().startswith("install"):
                    target = cmd_arg.strip()[len("install") :].strip()
                    if not target:
                        msg = "Usage: /plugin install <name-or-url>"
                    else:
                        try:
                            from silex_core.plugins.registry import get_registry

                            reg = get_registry()
                            if bridge.is_active:
                                await bridge.emit(
                                    {
                                        "type": "thinking",
                                        "data": {"status": f"Installing {target}..."},
                                    }
                                )
                            else:
                                console.print(
                                    f"  [bright_magenta]Installing {target}...[/]"
                                )
                            ok, msg = reg.install(target)
                            if ok:
                                # Auto-reload so the new plugin/skill is immediately active
                                loop.tool_registry._register_defaults()
                                if hasattr(loop, "skill_loader") and loop.skill_loader:
                                    loop.skill_loader.load_all()
                        except Exception as exc:
                            ok, msg = False, f"Install error: {exc}"
                    await _emit_or(msg, show_success if ok else show_error, msg)
                    continue

                elif cmd in (":plugin",) and cmd_arg.strip().startswith("uninstall"):
                    target = cmd_arg.strip()[len("uninstall") :].strip()
                    if not target:
                        msg = "Usage: /plugin uninstall <name>"
                    else:
                        try:
                            from silex_core.plugins.registry import get_registry

                            reg = get_registry()
                            ok, msg = reg.uninstall(target)
                            if ok:
                                loop.tool_registry._register_defaults()
                                if hasattr(loop, "skill_loader") and loop.skill_loader:
                                    loop.skill_loader.load_all()
                        except Exception as exc:
                            ok, msg = False, f"Uninstall error: {exc}"
                    await _emit_or(msg, show_success if ok else show_error, msg)
                    continue

                # ── Skills ────────────────────────────────────────────────────
                elif cmd in (":skills",):
                    if hasattr(loop, "skill_loader") and loop.skill_loader:
                        skills_list = loop.skill_loader.list_skills()
                        if not skills_list:
                            msg = "No skills loaded. Drop .md files into ~/.kinthic/skills/"
                        else:
                            lines = [f"Loaded skills ({len(skills_list)}):\n"]
                            for s in skills_list:
                                badge = {
                                    "core": "[core]",
                                    "verified": "[✓]",
                                    "community": "[comm]",
                                }.get(s["trust_level"], "")
                                lines.append(
                                    f"  {badge} {s['name']} v{s['version']} — {s['description']}"
                                )
                                if s.get("trigger"):
                                    lines.append(f"       trigger: {s['trigger']}")
                            lines.append(
                                "\nAdd skills: /plugin install <name>  |  "
                                "Drop .md into ~/.kinthic/skills/"
                            )
                            msg = "\n".join(lines)
                    else:
                        msg = "Skill loader not initialised."
                    await _emit_or(msg)
                    continue

                # ── MCP ─────────────────────────────────────────────────────
                elif cmd in (":mcp",):
                    mcp_sub = cmd_arg.strip().split(None, 1)
                    mcp_action = (
                        mcp_sub[0].lower() if mcp_sub and mcp_sub[0] else "list"
                    )
                    mcp_rest = mcp_sub[1].strip() if len(mcp_sub) > 1 else ""
                    try:
                        from silex_core.mcp.config import load_mcp_config, set_server_enabled
                        from silex_core.mcp.manager import get_mcp_manager

                        mgr = get_mcp_manager()
                        if mcp_action == "list":
                            cfg = load_mcp_config()
                            lines = ["MCP servers:\n"]
                            for srv_name, srv in cfg.servers.items():
                                state = (
                                    "enabled"
                                    if srv.get("enabled", True)
                                    else "disabled"
                                )
                                lines.append(f"  {srv_name}: {state}")
                            lines.extend(mgr.status_report())
                            msg = "\n".join(lines)
                        elif mcp_action == "reload":
                            count = await loop.tool_registry.reload_mcp_tools()
                            msg = f"Reloaded {count} MCP tool(s)."
                        elif mcp_action == "enable" and mcp_rest:
                            ok = set_server_enabled(mcp_rest, True)
                            await loop.tool_registry.reload_mcp_tools()
                            msg = (
                                f"Enabled '{mcp_rest}'."
                                if ok
                                else f"Server '{mcp_rest}' not found."
                            )
                        elif mcp_action == "disable" and mcp_rest:
                            ok = set_server_enabled(mcp_rest, False)
                            await loop.tool_registry.reload_mcp_tools()
                            msg = (
                                f"Disabled '{mcp_rest}'."
                                if ok
                                else f"Server '{mcp_rest}' not found."
                            )
                        elif mcp_action == "test" and mcp_rest:
                            ok, detail = await mgr.test_server(mcp_rest)
                            msg = f"[{'ok' if ok else 'fail'}] {detail}"
                        else:
                            msg = "Usage: :mcp list | reload | enable <name> | disable <name> | test <name>"
                    except Exception as exc:
                        msg = f"MCP error: {exc}"
                    await _emit_or(msg)
                    continue

                # ── Trajectory Export ─────────────────────────────────────────
                elif cmd in (":export-traj",):
                    # Parse mini flags: --format grpo|sft|csv  --success-only  --since YYYY-MM-DD
                    import shlex as _shlex

                    _args = _shlex.split(cmd_arg.strip()) if cmd_arg.strip() else []
                    _fmt = "grpo"
                    _success_only = False
                    _since = None
                    _i = 0
                    while _i < len(_args):
                        if _args[_i] == "--format" and _i + 1 < len(_args):
                            _fmt = _args[_i + 1]
                            _i += 2
                        elif _args[_i] == "--success-only":
                            _success_only = True
                            _i += 1
                        elif _args[_i] == "--since" and _i + 1 < len(_args):
                            _since = _args[_i + 1]
                            _i += 2
                        else:
                            _i += 1

                    if _fmt not in ("sft", "grpo", "csv"):
                        msg = f"Unknown format '{_fmt}'. Use sft, grpo, or csv."
                        await _emit_or(msg, show_error, msg)
                        continue

                    try:
                        from silex_core.autonomy.export import export_trajectories

                        if bridge.is_active:
                            await bridge.emit(
                                {
                                    "type": "thinking",
                                    "data": {"status": "Exporting trajectories..."},
                                }
                            )
                        else:
                            console.print(
                                "  [bright_magenta]Exporting trajectories...[/]"
                            )

                        records, path = await export_trajectories(
                            loop.db,
                            format=_fmt,
                            success_only=_success_only,
                            since=_since,
                        )
                        if path:
                            msg = (
                                f"Exported {len(records)} trajectories ({_fmt.upper()}) → {path}\n"
                                f"Compatible with: TRL GRPOTrainer, Atropos, Unsloth, Axolotl"
                            )
                        else:
                            msg = "No trajectories matched the filter criteria."
                    except Exception as exc:
                        msg = f"Export error: {exc}"
                    await _emit_or(msg, show_success, msg)
                    continue

                # ── Voice ─────────────────────────────────────────────────────
                elif cmd in (":voice",):
                    try:
                        from silex_core.voice.session import VoiceSession

                        mode = cmd_arg.strip().lower()
                        if mode == "off" and _voice_session:
                            _voice_session.stop()
                            _voice_session = None
                            msg = "Voice mode disabled."
                        elif not _voice_session:
                            _voice_session = VoiceSession(loop, bridge=bridge)
                            _voice_session.start()
                            msg = "Voice mode enabled. Speak to Kinthic."
                        else:
                            msg = "Voice already active. Say /voice off to disable."
                        await _emit_or(msg, show_success, msg)
                    except Exception as exc:
                        msg = f"Voice error: {exc}\nRun: pip install 'kinthic[voice]'"
                        await _emit_or(msg, show_error, msg)
                    continue

                # ── Clear ─────────────────────────────────────────────────────
                elif cmd in (":clear", ":cls"):
                    if bridge.is_active:
                        await bridge.emit(
                            {
                                "type": "response",
                                "data": {
                                    "text": "(Clear is unavailable in Ink mode — conversation history is preserved.)"
                                },
                            }
                        )
                    else:
                        console.clear()
                        show_banner()
                    continue

                # ── Unknown ───────────────────────────────────────────────────
                else:
                    unknown_msg = f"Unknown command: {cmd}. Type /help for options."
                    await _emit_or(unknown_msg, show_error, unknown_msg)
                    continue

            # ── Cognitive turn ───────────────────────────────────────────────
            # Save to history
            _append_history(user_input)
            session_history.append(user_input)
            if bridge.is_active and len(session_history) % 10 == 0:
                # Periodically sync history to Ink (for new entries)
                await bridge.emit(
                    {
                        "type": "history_update",
                        "data": {"history": session_history[-200:]},
                    }
                )

            try:
                t_start = time.monotonic()
                from datetime import datetime as _datetime, timezone as _timezone

                t_start_utc = _datetime.now(_timezone.utc).isoformat()

                from silex_core.ui.turn_emitter import TurnEmitter, worker_aware_emit

                turn_emitter: TurnEmitter | None = None
                event_emitter = bridge.emit
                if bridge.is_active:
                    turn_emitter = TurnEmitter(bridge.emit, mirror_legacy=False)
                    _turn_emitter_holder[0] = turn_emitter
                    await turn_emitter.user_message(user_input)
                    await turn_emitter.routing("Starting turn...")
                    event_emitter = worker_aware_emit(turn_emitter)

                # Create a cancellable task for the cognitive turn
                _current_process_task = asyncio.create_task(
                    loop.process(
                        user_input,
                        status_callback=None if bridge.is_active else None,
                        event_emitter=event_emitter,
                        turn_emitter=turn_emitter,
                    ),
                    name="kinthic-process",
                )

                if bridge.is_active:
                    # Race between cognitive turn and user cancel request
                    cancel_task = asyncio.create_task(
                        bridge.read_cancel_request(),
                        name="kinthic-cancel-watcher",
                    )
                    done, pending = await asyncio.wait(
                        [_current_process_task, cancel_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()
                        try:
                            await t
                        except asyncio.CancelledError:
                            pass

                    if _current_process_task not in done:
                        # User cancelled
                        await bridge.emit_cancel("Turn cancelled.")
                        _current_process_task = None
                        continue

                    if cancel_task in done and _current_process_task in done:
                        # Both finished — cancel arrived but process also finished; ignore cancel
                        pass

                    try:
                        response = _current_process_task.result()
                    except asyncio.CancelledError:
                        await bridge.emit_cancel("Turn cancelled.")
                        _current_process_task = None
                        continue
                else:
                    with console.status(
                        "[bright_cyan]  Kinthic is thinking...[/]",
                        spinner="dots",
                        spinner_style="bright_cyan",
                    ) as status:
                        response = await _current_process_task

                _current_process_task = None
                latency_ms = int((time.monotonic() - t_start) * 1000)

                # ── Tool-auth intercept ──────────────────────────────────────
                if bridge.is_active and response.tool_calls:
                    import json as _json
                    from silex_core.utils.config import KINTHIC_PENDING_EDITS
                    from silex_core.tools.code_editor import approve_edit_internally

                    if KINTHIC_PENDING_EDITS.exists():
                        try:
                            with open(KINTHIC_PENDING_EDITS) as _f:
                                pending = _json.load(_f)
                        except Exception:
                            pending = []

                        for edit in pending:
                            if edit.get("status") != "pending":
                                continue

                            target_lines = (
                                edit.get("target_content") or ""
                            ).splitlines()
                            replacement_lines = (
                                edit.get("replacement_content") or ""
                            ).splitlines()
                            diff_lines = [
                                {"type": "remove", "content": l}
                                for l in target_lines[:8]
                            ] + [
                                {"type": "add", "content": l}
                                for l in replacement_lines[:8]
                            ]

                            await bridge.emit(
                                {
                                    "type": "tool_auth",
                                    "data": {
                                        "toolName": "propose_code_edit",
                                        "targetPath": Path(
                                            edit.get("file_path", "")
                                        ).name,
                                        "operationType": "1 local file alteration",
                                        "txId": edit.get("id", ""),
                                        "diffLines": diff_lines,
                                    },
                                }
                            )

                            auth = await bridge.read_auth_response(timeout=120.0)

                            if auth and auth.get("approved"):
                                approve_edit_internally(edit["id"])
                                await bridge.emit({"type": "auth_complete"})
                            else:
                                edit["status"] = "rejected"
                                try:
                                    with open(KINTHIC_PENDING_EDITS, "w") as _f:
                                        _json.dump(pending, _f, indent=4)
                                except Exception:
                                    pass

                # ── Telemetry ────────────────────────────────────────────────
                session = loop.session.current
                tokens_used = 0
                tools_executed = 0
                if session:
                    tokens_row = await loop.db.fetch_one(
                        "SELECT SUM(input_tokens + output_tokens) AS total_tokens FROM llm_usage WHERE session_id = ? AND created_at >= ?",
                        (session.id, t_start_utc),
                    )
                    if tokens_row and tokens_row["total_tokens"] is not None:
                        tokens_used = tokens_row["total_tokens"]

                    tools_row = await loop.db.fetch_one(
                        "SELECT COUNT(*) AS count FROM action_logs WHERE session_id = ? AND turn_number = ?",
                        (session.id, session.turn_count),
                    )
                    if tools_row:
                        tools_executed = tools_row["count"]

                if bridge.is_active and turn_emitter is not None:
                    text = response.response or ""
                    await turn_emitter.assistant_done(text)
                    if response.new_memories:
                        await turn_emitter.memory(
                            len(response.new_memories),
                            [str(m)[:160] for m in response.new_memories[:5]],
                        )
                    await turn_emitter.turn_summary(
                        latency_ms=latency_ms,
                        tokens=tokens_used,
                        memories_written=len(response.new_memories),
                        tools_executed=tools_executed,
                        workers_used=turn_emitter.workers_used,
                    )
                    _turn_emitter_holder[0] = None
                elif bridge.is_active:
                    await bridge.emit(
                        {
                            "type": "telemetry",
                            "data": {
                                "latencyMs": latency_ms,
                                "tokens": tokens_used,
                                "memoriesWritten": len(response.new_memories),
                                "toolsExecuted": tools_executed,
                            },
                        }
                    )
                    await bridge.emit(
                        {
                            "type": "memory_write",
                            "data": {
                                "count": len(response.new_memories),
                                "items": [
                                    str(m)[:160] for m in response.new_memories[:5]
                                ],
                            },
                        }
                    )
                    text = response.response or ""
                    await bridge.emit({"type": "stream", "data": {"text": text}})
                else:
                    show_response(response)

                if _voice_session and _voice_session._active and response.response:
                    await _voice_session.speak(response.response)

            except KeyboardInterrupt:
                if bridge.is_active:
                    await bridge.emit_cancel("Thinking cancelled.")
                else:
                    console.print("\n  [dim]Thinking cancelled.[/]")
            except Exception as exc:
                if bridge.is_active:
                    await bridge.emit_error(str(exc))
                else:
                    show_error(str(exc))
                    console.print_exception(show_locals=False)

    except KeyboardInterrupt:
        console.print("\n\n  [dim]Interrupted. Shutting down...[/]\n")

    finally:
        if approval_task is not None:
            approval_task.cancel()
            try:
                await approval_task
            except asyncio.CancelledError:
                pass
        await bridge.stop()
        await loop.shutdown()


def main() -> None:
    """Synchronous wrapper for the async entry point."""
    import os

    if os.environ.get("KINTHIC_SKIP_SETUP") != "1":
        from silex_core.runtime.settings import RuntimeSettingsStore

        if not RuntimeSettingsStore().setup_status()["setup_completed"]:
            print("First run: starting setup wizard...")
            from scripts.cli import run_onboard

            run_onboard()
            return
    asyncio.run(run())


if __name__ == "__main__":
    main()
