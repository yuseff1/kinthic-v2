# Kinthic Performance & Token Efficiency

Kinthic is engineered to minimize latency and control token consumption without sacrificing agentic capabilities. We achieve this through progressive disclosure, context compression, and intent routing.

## 1. Progressive Skills Index
Unlike frameworks that inject the full markdown instructions of all 50+ skills into the system prompt (costing 20k+ tokens per turn), Kinthic uses **Progressive Disclosure**:
- The agent only sees a brief index of available tools (name + short description).
- If it needs to execute a complex multi-step workflow, it dynamically loads the full instructions into its context window for that specific task using the `skill_view` tool.
- **Win:** Reduces base prompt size from ~25k to ~3k tokens.

## 2. Fast Intent Routing (SmartRouter)
Not every message requires a frontier model's deep reasoning.
Kinthic employs a `SmartRouter` that evaluates the user's intent:
- **Chat Path**: Simple greetings or clarifications are routed to a fast, cheap model (e.g., Haiku or Gemini Flash).
- **Reasoning Path**: Complex planning or tool execution triggers the heavy model (e.g., Opus or GPT-4o).
- You can verify which model handled your last turn using the `/status` command in Telegram.

## 3. Context Compression
Kinthic's cognitive loop aggressively summarizes older memories. By offloading resolved goals to the SQLite graph database, the context window only retains the active `MemoryStore` window, dropping the cost of a long-running session by 80% over time.
