# WSL2 setup for Kinthic (Windows)

Kinthic runs on **Linux only**. On Windows, use **WSL2** (Windows Subsystem for Linux).

## 1. Enable WSL2

Open PowerShell **as Administrator**:

```powershell
wsl --install
```

Restart if prompted, then open **Ubuntu** from the Start menu.

Verify:

```bash
uname -a
# Should mention Microsoft / WSL
```

## 2. Install Kinthic (one command)

Inside your **WSL Ubuntu** terminal (not PowerShell):

```bash
curl -fsSL https://kinthic.openyf.dev/install.sh | bash
```

Reload your shell:

```bash
source ~/.bashrc
```

## 3. Initialize

```bash
kinthic init
```

This configures your LLM provider, installs core skills, optional Telegram pairing, and optional MCP servers.

## 4. Run

```bash
kinthic                  # terminal agent
kinthic channels telegram run  # messaging bot (after pairing)
kinthic doctor --ping    # verify API connectivity
```

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Running `curl \| bash` in PowerShell | Open WSL Ubuntu first |
| `kinthic: command not found` | `source ~/.bashrc` or open a new WSL tab |
| Provider ping fails | Re-run `kinthic init` and check API key in `~/.kinthic/.env` |

## Next steps

- [Quick start](quickstart.md)
- [MCP setup](mcp.md)
- [Telegram pairing](quickstart.md#deploy--server-docker)
