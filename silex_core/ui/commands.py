"""
silex/ui/commands.py — Canonical slash command registry for the Ink UI.

Single source of truth: this list MUST mirror every handler in scripts/run.py.
Sent to Ink at startup as an `init_commands` event for tab completion.
"""

SLASH_COMMANDS = [
    # ── General ──────────────────────────────────────────────────────────
    {"cmd": "/help", "args": "", "desc": "Show all commands"},
    {"cmd": "/quit", "args": "", "desc": "Exit Kinthic"},
    {"cmd": "/clear", "args": "", "desc": "Clear the screen"},
    # ── Memory ───────────────────────────────────────────────────────────
    {"cmd": "/memories", "args": "", "desc": "Show stored memories"},
    {"cmd": "/mem", "args": "", "desc": "Alias for /memories"},
    {"cmd": "/search", "args": "<query>", "desc": "Search memories"},
    {"cmd": "/remember", "args": "<fact>", "desc": "Manually store a memory"},
    {"cmd": "/forget", "args": "<number>", "desc": "Delete a memory by index"},
    # ── Goals ─────────────────────────────────────────────────────────────
    {"cmd": "/goals", "args": "", "desc": "Show active goals"},
    {"cmd": "/goal", "args": "<description>", "desc": "Add a new background goal"},
    # ── Session ──────────────────────────────────────────────────────────
    {"cmd": "/stats", "args": "", "desc": "Show session statistics"},
    {"cmd": "/sessions", "args": "", "desc": "List all past sessions"},
    {"cmd": "/export", "args": "", "desc": "Export current session"},
    # ── World Model ──────────────────────────────────────────────────────
    {
        "cmd": "/graph",
        "args": "[concept]",
        "desc": "Show knowledge graph stats or concept neighborhood",
    },
    {
        "cmd": "/why",
        "args": "<A> -> <B>",
        "desc": "Show causal chain between two concepts",
    },
    {"cmd": "/contradictions", "args": "", "desc": "Show detected contradictions"},
    {"cmd": "/contra", "args": "", "desc": "Alias for /contradictions"},
    {"cmd": "/hypotheses", "args": "", "desc": "Show pending hypotheses"},
    {"cmd": "/hypo", "args": "", "desc": "Alias for /hypotheses"},
    {"cmd": "/hypo-confirm", "args": "<uuid>", "desc": "Confirm a hypothesis"},
    {"cmd": "/hypo-deny", "args": "<uuid>", "desc": "Deny a hypothesis"},
    # ── Cognitive ────────────────────────────────────────────────────────
    {"cmd": "/improvements", "args": "", "desc": "Show improvement history"},
    {"cmd": "/imp", "args": "", "desc": "Alias for /improvements"},
    {"cmd": "/uncertainties", "args": "", "desc": "Show uncertainty flags"},
    {"cmd": "/unc", "args": "", "desc": "Alias for /uncertainties"},
    {"cmd": "/tools", "args": "", "desc": "List all registered tools"},

    {"cmd": "/benchmark", "args": "", "desc": "Run the benchmark suite"},
    {"cmd": "/bench", "args": "", "desc": "Alias for /benchmark"},
    {"cmd": "/meta", "args": "", "desc": "Run meta-reasoning analysis"},
    # ── Proposals ────────────────────────────────────────────────────────
    {"cmd": "/proposals", "args": "", "desc": "Show self-improvement proposals"},
    {"cmd": "/prop-approve", "args": "<uuid>", "desc": "Approve a proposal"},
    {"cmd": "/prop-reject", "args": "<uuid>", "desc": "Reject a proposal"},
    # ── Routing ──────────────────────────────────────────────────────────
    {
        "cmd": "/model",
        "args": "[provider]",
        "desc": "Show or switch the active LLM provider",
    },
    {
        "cmd": "/mode",
        "args": "speed|quality|auto",
        "desc": "Set routing mode for this session",
    },
    {"cmd": "/providers", "args": "", "desc": "List all providers and API key status"},
    # ── RAG ──────────────────────────────────────────────────────────────
    {
        "cmd": "/index",
        "args": "[path]",
        "desc": "Index a folder into vector DB for RAG",
    },
    {"cmd": "/rag", "args": "<query>", "desc": "Query the file index directly"},
    # ── Plugins & Skills ─────────────────────────────────────────────────
    {
        "cmd": ":plugins",
        "args": "",
        "desc": "List all registered tools (built-in + plugins)",
    },
    {"cmd": ":skills", "args": "", "desc": "List all loaded skills with metadata"},
    {
        "cmd": ":plugin",
        "args": "reload",
        "desc": "Hot-reload plugins and skills without restart",
    },
    {"cmd": ":plugin", "args": "search <query>", "desc": "Search KinthicHub catalog"},
    {
        "cmd": ":plugin",
        "args": "install <name>",
        "desc": "Install a skill or tool plugin from catalog or URL",
    },
    {
        "cmd": ":plugin",
        "args": "uninstall <name>",
        "desc": "Remove an installed skill or tool plugin",
    },
    # ── Training Data Export ─────────────────────────────────────────────
    {
        "cmd": "/export-traj",
        "args": "[--format grpo|sft|csv] [--success-only]",
        "desc": "Export trajectories as RL/SFT training data",
    },
    # ── Voice ────────────────────────────────────────────────────────────
    {"cmd": "/voice", "args": "[on|off]", "desc": "Toggle voice input/output mode"},
]
