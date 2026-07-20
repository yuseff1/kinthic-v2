---
title: "Model Context Protocol (MCP)"
description: "How to use Kinthic as the memory layer for other AI agents."
---

Kinthic isn't just a standalone agent; it is an **MCP Server**. 
The Model Context Protocol (MCP) allows you to expose Kinthic's powerful Silex memory engine to *other* AI clients, such as Claude Desktop or Cursor.

## Why use Kinthic with MCP?

If you use Claude Desktop for coding, Claude forgets everything when you start a new chat. By adding Kinthic as an MCP server, Claude gains access to the `silex_recall` and `silex_remember` tools. 

Now, you can tell Claude to "remember this architectural decision," and it will be saved persistently in Kinthic's SQLite database. Tomorrow, in a completely new chat, Claude can "recall architectural decisions" and pull that exact fact back from Kinthic!

## Setup with Claude Desktop

Connecting Kinthic to Claude Desktop takes 10 seconds.

1. Generate the configuration JSON:
```bash
kinthic mcp print-config
```

2. Copy the output block.

3. Open your Claude Desktop configuration file:
   - **Mac:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

4. Paste the configuration under the `mcpServers` key. It should look something like this:

```json
{
  "mcpServers": {
    "kinthic": {
      "command": "kinthic",
      "args": ["mcp", "serve", "--stdio"]
    }
  }
}
```

5. Restart Claude Desktop.

You will now see a little "Hammer" icon in Claude indicating that the Kinthic memory tools are connected and available!
