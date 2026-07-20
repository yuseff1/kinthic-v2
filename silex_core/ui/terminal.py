"""
Terminal UI — KINTHIC's Rich-based interface.

Provides a premium terminal experience with panels for reasoning traces,
responses, session stats, and interactive commands.

Polish additions:
  - Animated Rich spinner during thinking
  - Startup context summary (memory/goal recap)
  - New commands: :search, :forget, :remember, :sessions, :export
  - Improved help with categories
"""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree
from rich.theme import Theme
from rich import box

from silex_core.models.schemas import CognitiveResponse, Goal, Memory, Session

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

KINTHIC_THEME = Theme(
    {
        "kinthic.title": "bold bright_cyan",
        "kinthic.reasoning": "dim italic",
        "kinthic.response": "white",
        "kinthic.reflection": "dim magenta",
        "kinthic.confidence.high": "bold green",
        "kinthic.confidence.mid": "bold yellow",
        "kinthic.confidence.low": "bold red",
        "silex.memory": "cyan",
        "kinthic.goal": "yellow",
        "kinthic.stat": "bright_blue",
        "kinthic.command": "bold bright_green",
        "kinthic.error": "bold red",
        "kinthic.warning": "bold yellow",
        "kinthic.success": "bold green",
        "kinthic.dim": "dim white",
        "kinthic.accent": "bright_magenta",
    }
)

console = Console(theme=KINTHIC_THEME)


# ---------------------------------------------------------------------------
# Display Functions
# ---------------------------------------------------------------------------


def show_banner() -> None:
    """Display the KINTHIC startup banner."""
    _border_inner = 54  # characters between "    ║     " and closing "║"
    banner = Text()
    banner.append(
        "    ╔═══════════════════════════════════════════════════════════╗\n",
        style="bright_cyan",
    )
    banner.append(
        "    ║                                                           ║\n",
        style="bright_cyan",
    )
    banner.append(
        "    ║      █████╗ ██████╗ ██╗ █████╗                            ║\n",
        style="bright_cyan",
    )
    banner.append(
        "    ║     ██╔══██╗██╔══██╗██║██╔══██╗                           ║\n",
        style="bright_cyan",
    )
    banner.append(
        "    ║     ███████║██████╔╝██║███████║                            ║\n",
        style="bright_cyan",
    )
    banner.append(
        "    ║     ██╔══██║██╔══██╗██║██╔══██║                            ║\n",
        style="bright_cyan",
    )
    banner.append(
        "    ║     ██║  ██║██║  ██║██║██║  ██║                            ║\n",
        style="bright_cyan",
    )
    banner.append(
        "    ║     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═╝                            ║\n",
        style="bright_cyan",
    )
    banner.append(
        "    ║                                                           ║\n",
        style="bright_cyan",
    )
    banner.append(
        "    ║     "
        + "Local-first agent · memory · graph · governed tools".ljust(_border_inner)
        + "║\n",
        style="dim bright_cyan",
    )
    banner.append(
        "    ║     "
        + "Phase 02 — World Model + Reasoning".ljust(_border_inner)
        + "║\n",
        style="dim bright_cyan",
    )
    from silex import __version__

    banner.append(
        "    ║     " + f"v{__version__}".ljust(_border_inner) + "║\n",
        style="dim bright_cyan",
    )
    banner.append(
        "    ║                                                           ║\n",
        style="bright_cyan",
    )
    banner.append(
        "    ╚═══════════════════════════════════════════════════════════╝\n",
        style="bright_cyan",
    )
    console.print()
    console.print(banner)


def show_startup_summary(
    memory_count: int, goal_count: int, session_count: int, total_turns: int
) -> None:
    """Display a context-aware startup summary."""
    if memory_count == 0 and session_count <= 1:
        # First time
        console.print(
            "  [bright_cyan]◆[/] [dim]First session. VYN has no memories yet.[/]"
        )
        console.print(
            "  [dim]  Talk to VYN to start building knowledge. Type[/] "
            "[kinthic.command]:help[/] [dim]for commands.[/]\n"
        )
    else:
        # Returning
        console.print(
            f"  [bright_cyan]◆[/] [dim]Systems online.[/] "
            f"[silex.memory]{memory_count} memories[/] [dim]loaded,[/] "
            f"[kinthic.goal]{goal_count} active goals[/][dim],[/] "
            f"[kinthic.stat]{total_turns} total turns[/] [dim]across[/] "
            f"[kinthic.stat]{session_count} sessions[/][dim].[/]"
        )
        console.print(
            "  [dim]  Type your message or[/] [kinthic.command]:help[/] [dim]for commands.[/]\n"
        )


def show_response(cognitive: CognitiveResponse) -> None:
    """Display a full cognitive response with all panels."""

    # Combine Reasoning and Reflection into the Monologue Panel
    monologue = Text(cognitive.reasoning, style="kinthic.reasoning")

    reflection = cognitive.self_reflection.strip() if cognitive.self_reflection else ""
    if reflection and len(reflection) > 10:
        monologue.append("\n\n[🪞 Reflection]\n", style="bold magenta")
        monologue.append(reflection, style="kinthic.reflection")

    reasoning_panel = Panel(
        monologue,
        title="[bold bright_cyan]🧠 INTERNAL MONOLOGUE[/]",
        border_style="bright_cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )

    # Chat Response Panel
    chat_panel = Panel(
        Markdown(cognitive.response),
        title="[bold white]💬 VYN[/]",
        border_style="white",
        box=box.ROUNDED,
        padding=(1, 2),
    )

    # Create a layout table for split-screen
    grid = Table.grid(expand=True)
    grid.add_column("chat", ratio=3)
    grid.add_column("monologue", ratio=2)

    # Add some spacing between the columns
    grid.add_row(chat_panel, reasoning_panel)

    console.print()
    console.print(grid)

    # Status bar
    conf = cognitive.confidence
    if conf >= 0.7:
        conf_style = "kinthic.confidence.high"
        conf_icon = "●"
    elif conf >= 0.4:
        conf_style = "kinthic.confidence.mid"
        conf_icon = "◐"
    else:
        conf_style = "kinthic.confidence.low"
        conf_icon = "○"

    # Phase 2 counts
    causal_count = (
        len(cognitive.causal_observations) if cognitive.causal_observations else 0
    )
    contra_count = (
        len(cognitive.contradictions_detected)
        if cognitive.contradictions_detected
        else 0
    )
    hypo_count = len(cognitive.hypotheses) if cognitive.hypotheses else 0

    status_parts = [
        f"[{conf_style}]{conf_icon} {conf:.0%}[/]",
        f"[silex.memory]+{len(cognitive.new_memories)} mem[/]",
        f"[kinthic.goal]{len(cognitive.goal_updates)} goals[/]",
    ]

    if causal_count > 0:
        status_parts.append(f"[bright_cyan]+{causal_count} causal[/]")
    if contra_count > 0:
        status_parts.append(f"[bold red]{contra_count} conflict[/]")
    if hypo_count > 0:
        status_parts.append(f"[bright_magenta]{hypo_count} hypothesis[/]")

    if cognitive.uncertainty_flags:
        flags = ", ".join(cognitive.uncertainty_flags[:3])
        status_parts.append(f"[kinthic.dim]⚠ {flags}[/]")

    console.print("  " + "  │  ".join(status_parts))
    console.print()


def show_memories(memories: list[Memory]) -> None:
    """Display all stored memories in a table."""
    if not memories:
        console.print("\n  [kinthic.dim]No memories stored yet.[/]\n")
        return

    table = Table(
        title=f"🧠 VYN's Memories ({len(memories)} total)",
        box=box.ROUNDED,
        border_style="bright_cyan",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Content", style="white", max_width=55)
    table.add_column("Imp.", style="cyan", width=6, justify="center")
    table.add_column("Source", style="dim", width=10)
    table.add_column("Used", style="dim", width=5, justify="center")
    table.add_column("Tags", style="yellow", max_width=20)

    for i, mem in enumerate(memories, 1):
        imp_bar = "█" * int(mem.importance * 5)
        imp_bar = imp_bar.ljust(5, "░")
        tags = ", ".join(mem.tags[:3]) if mem.tags else "—"
        source = mem.source.value if hasattr(mem.source, "value") else str(mem.source)
        table.add_row(
            str(i),
            mem.content[:55],
            imp_bar,
            source,
            f"{mem.access_count}x",
            tags,
        )

    console.print()
    console.print(table)
    console.print(
        "  [kinthic.dim]Use[/] [kinthic.command]:forget <#>[/] [kinthic.dim]to remove a memory.[/]"
    )
    console.print()


def show_search_results(memories: list[Memory], query: str) -> None:
    """Display search results."""
    if not memories:
        console.print(f"\n  [kinthic.dim]No memories matching '{query}'.[/]\n")
        return

    table = Table(
        title=f"🔍 Search: '{query}' ({len(memories)} results)",
        box=box.ROUNDED,
        border_style="bright_cyan",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Content", style="white", max_width=60)
    table.add_column("Imp.", style="cyan", width=6, justify="center")
    table.add_column("Source", style="dim", width=10)

    for i, mem in enumerate(memories, 1):
        imp_bar = "█" * int(mem.importance * 5)
        imp_bar = imp_bar.ljust(5, "░")
        source = mem.source.value if hasattr(mem.source, "value") else str(mem.source)
        table.add_row(str(i), mem.content[:60], imp_bar, source)

    console.print()
    console.print(table)
    console.print()


def show_goals(goals: list[Goal]) -> None:
    """Display goals in a formatted table."""
    if not goals:
        console.print("\n  [kinthic.dim]No goals tracked yet.[/]\n")
        return

    table = Table(
        title=f"🎯 VYN's Goals ({len(goals)} total)",
        box=box.ROUNDED,
        border_style="yellow",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Goal", style="white", max_width=50)
    table.add_column("Priority", width=10)
    table.add_column("Status", width=12)
    table.add_column("Notes", style="dim", max_width=30)

    priority_colors = {
        "critical": "bold red",
        "high": "bold yellow",
        "medium": "white",
        "low": "dim",
    }
    status_icons = {
        "active": "🟢 active",
        "completed": "✅ done",
        "abandoned": "❌ dropped",
        "blocked": "🔴 blocked",
    }

    for i, goal in enumerate(goals, 1):
        p_val = (
            goal.priority.value
            if hasattr(goal.priority, "value")
            else str(goal.priority)
        )
        s_val = goal.status.value if hasattr(goal.status, "value") else str(goal.status)
        table.add_row(
            str(i),
            goal.description,
            Text(p_val.upper(), style=priority_colors.get(p_val, "white")),
            status_icons.get(s_val, s_val),
            goal.completion_notes or "—",
        )

    console.print()
    console.print(table)
    console.print()


def show_stats(info: dict) -> None:
    """Display session statistics."""
    table = Table(
        title="📊 Session Statistics",
        box=box.ROUNDED,
        border_style="bright_blue",
        padding=(0, 1),
    )
    table.add_column("Metric", style="bright_blue")
    table.add_column("Value", style="white")

    table.add_row("Session ID", info["session_id"])
    table.add_row("Turns (this session)", str(info["turn_count"]))
    table.add_row("Turns (all time)", str(info["total_turns"]))
    table.add_row("Total memories", str(info["total_memories"]))
    table.add_row("Knowledge nodes", str(info.get("graph_nodes", 0)))
    table.add_row("Causal edges", str(info.get("graph_edges", 0)))
    table.add_row("Active goals", str(info["active_goals"]))
    table.add_row("Memories (this session)", str(info["memories_this_session"]))
    table.add_row("Avg confidence", f"{info['avg_confidence']:.0%}")

    console.print()
    console.print(table)
    console.print()


def show_sessions(sessions: list[Session]) -> None:
    """Display session history."""
    if not sessions:
        console.print("\n  [kinthic.dim]No past sessions.[/]\n")
        return

    table = Table(
        title=f"📜 Session History ({len(sessions)} sessions)",
        box=box.ROUNDED,
        border_style="bright_blue",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Session ID", style="bright_blue", width=10)
    table.add_column("Started", style="white", width=20)
    table.add_column("Turns", style="cyan", width=6, justify="center")
    table.add_column("Memories", style="cyan", width=8, justify="center")
    table.add_column("Confidence", style="white", width=10, justify="center")

    for i, sess in enumerate(sessions, 1):
        started = sess.started_at[:19].replace("T", " ")
        conf = f"{sess.avg_confidence:.0%}" if sess.avg_confidence > 0 else "—"
        table.add_row(
            str(i),
            sess.id[:8],
            started,
            str(sess.turn_count),
            str(sess.memories_created),
            conf,
        )

    console.print()
    console.print(table)
    console.print()


def show_help() -> None:
    """Display available commands with categories."""
    help_text = """[bold bright_white]💭 Conversation[/]
  Just type your message to talk to VYN.

[bold bright_white]🧠 Memory[/]
  [kinthic.command]:memories[/]          Show all stored memories
  [kinthic.command]:search <query>[/]    Search memories by keyword
  [kinthic.command]:remember <fact>[/]   Manually store a memory
  [kinthic.command]:forget <#>[/]        Delete a memory by its number

[bold bright_white]🌐 World Model[/]  [dim](Phase 2)[/]
  [kinthic.command]:graph[/]             Show knowledge graph statistics
  [kinthic.command]:graph <concept>[/]   Show neighborhood of a concept
  [kinthic.command]:why <A> -> <B>[/]    Find causal chain from A to B
  [kinthic.command]:contradictions[/]    Show unresolved contradictions
  [kinthic.command]:hypotheses[/]        Show pending predictions
  [kinthic.command]:hypo-confirm <id>[/]  Mark a hypothesis confirmed (UUID)
  [kinthic.command]:hypo-deny <id>[/]    Mark a hypothesis denied (UUID)

[bold bright_white]🎯 Goals[/]
  [kinthic.command]:goals[/]             Show all goals (active and completed)

[bold bright_white]📈 Self-Improvement[/]  [dim](Phase 3)[/]
  [kinthic.command]:improvements[/]      Show recent self-corrections

[bold bright_white]🛠️ Tool Use[/]  [dim](Phase 5)[/]
  [kinthic.command]:tools[/]             Show registered tools

[bold bright_white]🔄 Self-Improvement[/]  [dim](Phase 7)[/]
  [kinthic.command]:proposals[/]         Show pending improvement proposals
  [kinthic.command]:prop-approve <uuid>[/]  Mark proposal approved (human review)
  [kinthic.command]:prop-reject <uuid>[/]   Mark proposal rejected
  [kinthic.command]:benchmark[/]         Run the capability benchmark suite
  [kinthic.command]:meta[/]              Trigger meta-reasoning analysis

[bold bright_white]📊 Info[/]
  [kinthic.command]:stats[/]             Show session statistics
  [kinthic.command]:sessions[/]          Show past session history

[bold bright_white]🤖 Routing[/]
  [kinthic.command]/providers[/]        List all providers and API key status
  [kinthic.command]/model <name>[/]     Switch the active LLM provider
  [kinthic.command]/mode <mode>[/]      Set routing mode (speed|quality|auto|local)

[bold bright_white]🔌 Plugins[/]  [dim](Phase D)[/]
  [kinthic.command]/plugins[/]           List all registered tools (built-in + user plugins)
  [kinthic.command]/plugin reload[/]     Hot-reload user plugins without restarting

[bold bright_white]📂 File RAG[/]  [dim](Phase C)[/]
  [kinthic.command]/index [path][/]      Index a folder into the vector DB
  [kinthic.command]/rag <query>[/]       Search the file index directly

[bold bright_white]🎤 Voice I/O[/]  [dim](Phase E)[/]
  [kinthic.command]/voice [on|off][/]    Toggle voice input/output mode

[bold bright_white]⚙ System[/]
  [kinthic.command]:clear[/]             Clear the screen
  [kinthic.command]:export[/]            Export session to JSON
  [kinthic.command]:help[/]              Show this help message
  [kinthic.command]:quit[/]              Exit VYN (memories are saved)

  [dim]* Note: Commands can be run with either '/' or ':' prefix.[/]"""

    console.print()
    console.print(
        Panel(
            help_text,
            title="[bold bright_green]⌨ Commands[/]",
            border_style="bright_green",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


def show_error(message: str) -> None:
    """Display an error message."""
    console.print(f"\n  [kinthic.error]✗ Error:[/] {message}\n")


def show_warning(message: str) -> None:
    """Display a warning message."""
    console.print(f"\n  [kinthic.warning]⚠ {message}[/]\n")


def show_success(message: str) -> None:
    """Display a success message."""
    console.print(f"\n  [kinthic.success]✓ {message}[/]\n")


def show_info(message: str) -> None:
    """Display an info message."""
    console.print(f"\n  [bright_cyan]◆[/] [dim]{message}[/]\n")


# ---------------------------------------------------------------------------
# Phase 2 Display Functions
# ---------------------------------------------------------------------------


def show_graph_stats(stats: dict) -> None:
    """Display knowledge graph statistics."""
    table = Table(
        title="🌐 Knowledge Graph",
        box=box.ROUNDED,
        border_style="bright_cyan",
        padding=(0, 1),
    )
    table.add_column("Metric", style="bright_cyan")
    table.add_column("Value", style="white")

    table.add_row("Total nodes", str(stats["total_nodes"]))
    table.add_row("Total edges", str(stats["total_edges"]))
    table.add_row("Connected components", str(stats["connected_components"]))

    if stats.get("node_types"):
        for nt, count in stats["node_types"].items():
            table.add_row(f"  {nt} nodes", str(count))

    if stats.get("edge_types"):
        for et, count in stats["edge_types"].items():
            table.add_row(f"  {et} edges", str(count))

    console.print()
    console.print(table)
    console.print()


def show_graph_neighborhood(data: dict) -> None:
    """Display the neighborhood of a concept as a Rich tree."""
    if not data or not data.get("center"):
        console.print("\n  [kinthic.dim]Concept not found in the graph.[/]\n")
        return

    tree = Tree(f"[bold bright_cyan]🌐 {data['center']}[/]")

    for edge in data.get("edges", []):
        from_label = edge["from"]
        to_label = edge["to"]
        etype = edge["type"]
        strength = edge["strength"]

        strength_bar = "█" * int(strength * 5)
        strength_bar = strength_bar.ljust(5, "░")

        if from_label == data["center"][:40]:
            tree.add(
                f"[white]──[{etype}]──▶[/] [bright_white]{to_label}[/] "
                f"[dim]{strength_bar}[/]"
            )
        else:
            tree.add(
                f"[dim]{from_label}[/] [white]──[{etype}]──▶[/] "
                f"[bright_cyan](this)[/] [dim]{strength_bar}[/]"
            )

    console.print()
    console.print(tree)
    console.print(
        f"  [kinthic.dim]{len(data.get('nodes', []))} nodes, "
        f"{len(data.get('edges', []))} edges in neighborhood[/]"
    )
    console.print()


def show_causal_chain(chain: list[dict], from_concept: str, to_concept: str) -> None:
    """Display a causal chain between two concepts."""
    if not chain:
        console.print(
            f"\n  [kinthic.dim]No causal path found from "
            f"'{from_concept}' to '{to_concept}'.[/]\n"
        )
        return

    console.print()
    console.print(
        f"  [bold bright_cyan]🔗 Causal Chain:[/] "
        f"[white]{from_concept}[/] → [white]{to_concept}[/]"
    )
    console.print()

    for i, step in enumerate(chain):
        strength_bar = "█" * int(step["strength"] * 5)
        strength_bar = strength_bar.ljust(5, "░")
        if i == 0:
            console.print(f"  [bright_white]{step['from']}[/]")
        console.print(f"    │ [dim]{step['relationship']}[/] [dim]{strength_bar}[/]")
        console.print("    ▼")
        console.print(f"  [bright_white]{step['to']}[/]")

    console.print()


def show_contradictions(contradictions) -> None:
    """Display contradictions."""
    if not contradictions:
        console.print("\n  [kinthic.dim]No unresolved contradictions.[/]\n")
        return

    table = Table(
        title=f"⚡ Contradictions ({len(contradictions)} unresolved)",
        box=box.ROUNDED,
        border_style="red",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Analysis", style="white", max_width=60)
    table.add_column("Status", style="dim", width=12)
    table.add_column("Created", style="dim", width=20)

    for i, c in enumerate(contradictions, 1):
        created = c.created_at[:19].replace("T", " ")
        status_icon = "🔴 open" if c.status == "unresolved" else "✅ resolved"
        table.add_row(str(i), c.analysis[:60], status_icon, created)

    console.print()
    console.print(table)
    console.print()


def show_hypotheses(hypotheses) -> None:
    """Display hypotheses."""
    if not hypotheses:
        console.print("\n  [kinthic.dim]No pending hypotheses.[/]\n")
        return

    table = Table(
        title=f"💡 Hypotheses ({len(hypotheses)} pending)",
        box=box.ROUNDED,
        border_style="bright_magenta",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Prediction", style="white", max_width=50)
    table.add_column("Reasoning", style="dim", max_width=30)
    table.add_column("Status", width=12)

    status_icons = {
        "pending": "🟡 pending",
        "confirmed": "✅ confirmed",
        "denied": "❌ denied",
    }

    for i, h in enumerate(hypotheses, 1):
        table.add_row(
            str(i),
            h.claim[:50],
            h.reasoning[:30],
            status_icons.get(h.status, h.status),
        )

    console.print()
    console.print(table)
    console.print()


def show_improvements(improvements) -> None:
    """Display recent self-improvements."""
    if not improvements:
        console.print("\n  [kinthic.dim]No self-improvements logged yet.[/]\n")
        return

    table = Table(
        title=f"📈 Recent Self-Corrections ({len(improvements)})",
        box=box.ROUNDED,
        border_style="bright_green",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Turn", style="dim", width=6)
    table.add_column("Scores (A/D/H)", style="yellow", width=14)
    table.add_column("Critic Feedback", style="white", max_width=40)
    table.add_column("Improved Response", style="bright_cyan", max_width=50)

    for imp in improvements:
        scores = (
            f"{imp.accuracy_score:.1f}/{imp.depth_score:.1f}/{imp.honesty_score:.1f}"
        )
        table.add_row(
            str(imp.turn_number),
            scores,
            imp.feedback[:100] + "..." if len(imp.feedback) > 100 else imp.feedback,
            imp.improved_response[:100] + "..."
            if len(imp.improved_response) > 100
            else imp.improved_response,
        )

    console.print()
    console.print(table)
    console.print()


def show_debate_resolution(resolution) -> None:
    """Display the Judge's synthesis of a debate."""
    console.print()
    console.print(
        Panel(
            f"[bold bright_white]The Judge's Synthesis[/]\n\n"
            f"[dim]Summary:[/] {resolution.summary}\n\n"
            f"[bold bright_cyan]Final Truth:[/] {resolution.synthesis}",
            title="[bold green]⚖️ Debate Concluded[/]",
            border_style="green",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    console.print()


def show_uncertainties(uncertainties) -> None:
    """Display tracked uncertainties."""
    if not uncertainties:
        console.print("\n  [kinthic.dim]No known uncertainties tracked.[/]\n")
        return

    table = Table(
        title=f"❓ Known Disagreements / Uncertainties ({len(uncertainties)})",
        box=box.ROUNDED,
        border_style="bright_magenta",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Topic", style="white", max_width=30)
    table.add_column("Why Uncertain", style="dim", max_width=50)

    for u in uncertainties:
        table.add_row(
            u.topic[:50],
            u.why_uncertain[:80] + "..."
            if len(u.why_uncertain) > 80
            else u.why_uncertain,
        )

    console.print()
    console.print(table)
    console.print()


def show_tools(registry) -> None:
    """Display available tools in the registry."""
    if not registry or not registry.tools:
        console.print("\n  [kinthic.dim]No tools registered.[/]\n")
        return

    table = Table(
        title=f"🛠️ Registered Tools ({len(registry.tools)})",
        box=box.ROUNDED,
        border_style="cyan",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Tool Name", style="white", width=15)
    table.add_column("Description", style="dim", max_width=40)
    table.add_column("Arguments Schema", style="magenta", max_width=30)

    for name, tool in registry.tools.items():
        table.add_row(name, tool.description, str(tool.schema))

    console.print()
    console.print(table)
    console.print()


def show_principles(principles) -> None:
    """Display discovered universal principles."""
    if not principles:
        console.print(
            "\n  [kinthic.dim]No universal principles discovered yet. Keep chatting![/]\n"
        )
        return

    table = Table(
        title=f"📐 Universal Principles ({len(principles)} discovered)",
        box=box.ROUNDED,
        border_style="bright_yellow",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Name", style="bold bright_yellow", width=22)
    table.add_column("Statement", style="white", max_width=40)
    table.add_column("Learned From", style="dim", width=15)
    table.add_column("Also Applies To", style="cyan", max_width=25)

    for p in principles:
        domains = ", ".join(p.applicable_domains[:3])
        if len(p.applicable_domains) > 3:
            domains += f" (+{len(p.applicable_domains) - 3})"
        table.add_row(
            p.name,
            p.statement[:80] + "..." if len(p.statement) > 80 else p.statement,
            p.original_domain,
            domains,
        )

    console.print()
    console.print(table)
    console.print()


def show_proposals(proposals) -> None:
    """Display pending self-improvement proposals."""
    if not proposals:
        console.print("\n  [kinthic.dim]No pending self-improvement proposals.[/]\n")
        return

    for p in proposals:
        panel = Panel(
            f"[bold white]Target:[/] {p.target_system}\n"
            f"[bold white]Change:[/] {p.description}\n"
            f"[bold white]Rationale:[/] {p.rationale}\n"
            f"[bold white]Success Metric:[/] {p.success_metric}\n"
            f"[dim]Full ID (for :prop-approve / :prop-reject):[/]\n[white]{p.id}[/]\n"
            f"[dim]Status: {p.status} | {p.created_at[:10]}[/]",
            title="🔄 Self-Improvement Proposal",
            border_style="bright_red",
            padding=(1, 2),
        )
        console.print()
        console.print(panel)
    console.print()


def show_benchmark_result(result) -> None:
    """Display a benchmark result with scores."""
    if not result:
        console.print("\n  [kinthic.dim]No benchmark results.[/]\n")
        return

    # Score color
    score = result.total_score
    if score >= 80:
        color = "bright_green"
    elif score >= 60:
        color = "bright_yellow"
    else:
        color = "bright_red"

    panel = Panel(
        f"[bold {color}]Overall Score: {score:.1f} / 100.0[/]\n\n"
        f"  [white]Accuracy:[/]  {result.accuracy_avg:.3f}\n"
        f"  [white]Depth:[/]     {result.depth_avg:.3f}\n"
        f"  [white]Honesty:[/]   {result.honesty_avg:.3f}\n\n"
        f"  [dim]Questions: {result.question_count} | "
        f"Domains: {', '.join(result.domains_tested)}[/]",
        title="📊 Benchmark Results",
        border_style=color,
        padding=(1, 2),
    )
    console.print()
    console.print(panel)

    # Show trend if we have history
    console.print()


def show_meta_proposal(proposal) -> None:
    """Display a meta-analysis proposal with alarm styling."""
    if not proposal:
        console.print(
            "\n  [kinthic.dim]Meta-analysis found no actionable improvements.[/]\n"
        )
        return

    panel = Panel(
        f"[bold bright_red]⚠  VYN HAS PROPOSED A CHANGE TO HERSELF  ⚠[/]\n\n"
        f"[bold white]Target System:[/] {proposal.target_system}\n"
        f"[bold white]Proposed Change:[/] {proposal.description}\n"
        f"[bold white]Rationale:[/] {proposal.rationale}\n"
        f"[bold white]Success Metric:[/] {proposal.success_metric}\n\n"
        f"[dim italic]This proposal requires YOUR approval before implementation.\n"
        f"ID: {proposal.id[:8]} | Status: {proposal.status}[/]",
        title="🔒 SAFETY LOCK — Human Approval Required",
        border_style="bold bright_red",
        padding=(1, 2),
    )
    console.print()
    console.print(panel)
    console.print()


def get_input() -> str:
    """Get user input with a styled prompt."""
    try:
        return console.input("\n  [bold bright_white]You ›[/] ").strip()
    except (EOFError, KeyboardInterrupt):
        return ":quit"
