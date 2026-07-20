# Kinthic Migration Guide

Kinthic provides a built-in migration tool to safely import your skills, personas, and configurations from other agent frameworks like **Hermes** and **OpenClaw**.

## How it works

The `kinthic migrate` tool scans your existing framework's configuration directory, identifies migratable assets, and imports them into your `~/.kinthic` directory. 

**Imported Skills Trust**: All imported skills are explicitly marked as `community` trust (not `core`), ensuring they adhere to Kinthic's strict security sandboxing and do not inherit elevated privileges by default.

**Secrets Migration**: Hermes `.env` files are parsed and imported into the `secrets.json` file in Kinthic.

## Hermes Migration

Hermes typically stores its configuration in `~/.hermes/`. Kinthic will scan for:
- `config.yaml`
- `.env` (API keys)
- `skills/` directory
- `memories/USER.md` (Persona identity)

**Commands:**
```bash
# 1. Scan the Hermes directory to see what will be migrated
kinthic migrate scan --from hermes

# 2. Perform a dry-run to ensure there are no conflicts
kinthic migrate import --from hermes --dry-run

# 3. Apply the migration
kinthic migrate import --from hermes --apply
```

## OpenClaw Migration

OpenClaw stores its configuration in `~/.openclaw/`. Kinthic will scan for:
- `openclaw.json` (General settings and allowlists)
- `workspace/` directory (Markdown skills and `SOUL.md` identity)

**Commands:**
```bash
# 1. Scan the OpenClaw directory
kinthic migrate scan --from openclaw

# 2. Perform a dry-run
kinthic migrate import --from openclaw --dry-run

# 3. Apply the migration
kinthic migrate import --from openclaw --apply
```

## Post-Migration Security Check

After successfully importing data, **you must re-pair your Telegram account**.
This ensures the imported configuration doesn't accidentally grant unauthorized access.

1. Start Kinthic: `kinthic telegram`
2. Open Telegram and send: `/pair`
3. Enter your secret passcode.
