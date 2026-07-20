"""
silex_core/plugins/registry.py — KinthicHub local plugin & skill registry.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import time
import urllib.request
from typing import Any

log = logging.getLogger("silex.plugins.registry")

DEFAULT_REGISTRY_URL = os.getenv(
    "KINTHIC_REGISTRY_URL",
    "https://kinthic.openyf.dev/registry/catalog.yaml",
)
MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024  # 5 MiB


class KinthicRegistry:
    """Local plugin/skill registry backed by ~/.kinthic/registry/catalog.yaml."""

    def __init__(self) -> None:
        from silex_core.utils.config import KINTHIC_HOME

        self.registry_dir = KINTHIC_HOME / "registry"
        self.catalog_path = self.registry_dir / "catalog.yaml"
        self._catalog: list[dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    # Catalog I/O
    # ------------------------------------------------------------------

    def _ensure_dir(self) -> None:
        self.registry_dir.mkdir(parents=True, exist_ok=True)

    def load_catalog(self) -> list[dict[str, Any]]:
        """Load and return all catalog entries (seeding if first run)."""
        if self._catalog is not None:
            return self._catalog

        self._ensure_dir()
        if not self.catalog_path.exists():
            self.seed_builtin_catalog()
        else:
            self._catalog = self._read_catalog_file()

        self._sync_installed_flags(self._catalog or [])
        return self._catalog or []

    def _read_catalog_file(self) -> list[dict[str, Any]]:
        try:
            import yaml

            with open(self.catalog_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("entries", [])
        except Exception as exc:
            log.warning("Could not read catalog: %s", exc)
            return []

    def _write_catalog(self, entries: list[dict]) -> None:
        self._ensure_dir()
        try:
            import yaml

            payload = {
                "version": "1.0",
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "entries": entries,
            }
            with open(self.catalog_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True)
            self._catalog = entries
        except Exception as exc:
            log.error("Failed to write catalog: %s", exc)

    # ------------------------------------------------------------------
    # Seed from bundled assets
    # ------------------------------------------------------------------

    def seed_builtin_catalog(self) -> None:
        """Build catalog from bundled skills + provider plugins."""
        from silex_core.utils.config import PROJECT_ROOT

        bundled_catalog = PROJECT_ROOT / "registry" / "catalog.yaml"
        if bundled_catalog.exists():
            try:
                import yaml

                with open(bundled_catalog, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                entries = list(data.get("entries", []))
                if entries:
                    log.info(
                        "Seeded KinthicHub catalog from bundled registry/catalog.yaml (%d entries)",
                        len(entries),
                    )
                    self._write_catalog(entries)
                    self._sync_installed_flags(entries)
                    return
            except Exception as exc:
                log.warning("Could not load bundled catalog.yaml: %s", exc)

        entries: list[dict] = []

        # 1. Bundled skills from repo skills/*.md
        skills_dir = PROJECT_ROOT / "skills"
        if skills_dir.exists():
            for md in sorted(skills_dir.glob("*.md")):
                if md.stem.lower() in {"readme"}:
                    continue
                desc = ""
                for line in md.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip().lstrip("#").strip()
                    if stripped:
                        desc = stripped[:120]
                        break
                entries.append(
                    {
                        "name": md.stem,
                        "type": "skill",
                        "version": "1.0.0",
                        "description": desc,
                        "tags": ["bundled"],
                        "trust_level": "core",
                        "source": "bundled",
                        "entry_file": md.name,
                        "installed": True,
                    }
                )

        # 2. Bundled provider plugins from repo plugins/providers/
        providers_dir = PROJECT_ROOT / "plugins" / "providers"
        if providers_dir.exists():
            for provider_dir in sorted(providers_dir.iterdir()):
                if not provider_dir.is_dir():
                    continue
                yaml_path = provider_dir / "plugin.yaml"
                if not yaml_path.exists():
                    continue
                try:
                    import yaml

                    with open(yaml_path, encoding="utf-8") as f:
                        manifest = yaml.safe_load(f) or {}
                    entries.append(
                        {
                            "name": manifest.get("name", provider_dir.name),
                            "type": "provider",
                            "version": "1.0.0",
                            "description": manifest.get("description", ""),
                            "tags": ["provider", "llm"],
                            "trust_level": "core",
                            "source": "bundled",
                            "entry_file": "plugin.yaml",
                            "installed": True,
                        }
                    )
                except Exception:
                    pass

        log.info("Seeded KinthicHub catalog with %d entries", len(entries))
        self._write_catalog(entries)
        self._sync_installed_flags(entries)

    def _skill_present_on_disk(self, name: str) -> bool:
        """Return True if a catalog entry appears to be installed locally."""
        from silex_core.utils.config import (
            KINTHIC_PLUGINS_SKILLS,
            KINTHIC_PLUGINS_TOOLS,
            KINTHIC_SKILLS,
        )

        if not name:
            return False
        if (KINTHIC_SKILLS / f"{name}.md").exists():
            return True
        if (KINTHIC_SKILLS / name).is_dir():
            return True
        if (KINTHIC_PLUGINS_SKILLS / name).is_dir():
            return True
        if (KINTHIC_PLUGINS_TOOLS / name).is_dir():
            return True
        return False

    def _sync_installed_flags(self, entries: list[dict[str, Any]]) -> None:
        """Reconcile catalog installed flags with files on disk."""
        changed = False
        for entry in entries:
            name = entry.get("name", "")
            present = self._skill_present_on_disk(name)
            if entry.get("installed") != present:
                entry["installed"] = present
                changed = True
        if changed:
            self._write_catalog(entries)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self, query: str, type_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """Fuzzy-search catalog by name, description, and tags."""
        catalog = self.load_catalog()
        q = query.lower()
        results = []
        for entry in catalog:
            if type_filter and entry.get("type") != type_filter:
                continue
            score = 0
            name = entry.get("name", "").lower()
            desc = entry.get("description", "").lower()
            tags = " ".join(entry.get("tags", [])).lower()
            if q in name:
                score += 3
            if q in desc:
                score += 2
            if q in tags:
                score += 1
            if score:
                results.append((score, entry))
        results.sort(key=lambda x: -x[0])
        return [e for _, e in results]

    # ------------------------------------------------------------------
    # Install / Uninstall
    # ------------------------------------------------------------------

    def install(self, name_or_url: str) -> tuple[bool, str]:
        """Install a skill or tool plugin."""
        from silex_core.utils.config import KINTHIC_SKILLS, KINTHIC_PLUGINS_TOOLS

        catalog = self.load_catalog()

        # Try catalog lookup first
        entry = next((e for e in catalog if e.get("name") == name_or_url), None)

        if entry is None and name_or_url.startswith("https://"):
            entry = {
                "name": name_or_url.split("/")[-1].split(".")[0],
                "type": "skill" if name_or_url.endswith(".md") else "tool",
                "url": name_or_url,
                "sha256": "",
                "trust_level": "community",
                "source": "remote",
            }

        if entry is None:
            return (
                False,
                f"'{name_or_url}' not found in catalog. Try: kinthic skills search {name_or_url}",
            )

        if entry.get("installed"):
            return False, f"'{entry['name']}' is already installed."

        if entry.get("source") == "bundled" or entry.get("trust_level") == "core":
            ok, msg = self.install_bundled(entry["name"])
            if ok:
                self._mark_installed(entry["name"])
            return ok, msg

        url = entry.get("url", "")
        if not url:
            return False, f"Catalog entry '{entry['name']}' has no download URL."

        try:
            log.info("Downloading %s from %s", entry["name"], url)
            if not url.startswith("https://"):
                return False, "Only https:// URLs are supported for remote installs."
            content_bytes = self._download_bytes(url, MAX_DOWNLOAD_BYTES)

            # Integrity check
            if entry.get("sha256"):
                actual = hashlib.sha256(content_bytes).hexdigest()
                if actual != entry["sha256"]:
                    return False, (
                        f"SHA-256 mismatch for '{entry['name']}'. "
                        f"Expected {entry['sha256']}, got {actual}. Aborting."
                    )

            plugin_type = entry.get("type", "skill")

            if plugin_type == "skill":
                dest = KINTHIC_SKILLS / f"{entry['name']}.md"
                dest.write_bytes(content_bytes)
                self._mark_installed(entry["name"])
                return True, f"Skill '{entry['name']}' installed to {dest}"

            elif plugin_type == "tool":
                import io
                import zipfile

                plugin_dest = KINTHIC_PLUGINS_TOOLS / entry["name"]
                plugin_dest.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(io.BytesIO(content_bytes)) as zf:
                    self._safe_extract_zip(zf, plugin_dest)
                self._mark_installed(entry["name"])
                return True, f"Tool plugin '{entry['name']}' installed to {plugin_dest}"

            else:
                return (
                    False,
                    f"Cannot auto-install type='{plugin_type}' — install manually.",
                )

        except Exception as exc:
            return False, f"Install failed: {exc}"

    def install_bundled(self, name: str) -> tuple[bool, str]:
        """Copy a bundled skill from the repo into ~/.kinthic/skills/."""
        from silex_core.utils.config import PROJECT_ROOT, KINTHIC_SKILLS

        KINTHIC_SKILLS.mkdir(parents=True, exist_ok=True)
        src_md = PROJECT_ROOT / "skills" / f"{name}.md"
        if not src_md.exists():
            return (
                False,
                f"Bundled skill '{name}' not found in package (missing {src_md.name}).",
            )

        dest_md = KINTHIC_SKILLS / f"{name}.md"
        shutil.copy2(src_md, dest_md)

        for suffix in (".yaml", ".skill.yaml"):
            src_yaml = PROJECT_ROOT / "skills" / f"{name}{suffix}"
            if src_yaml.exists():
                shutil.copy2(src_yaml, KINTHIC_SKILLS / src_yaml.name)
                break

        return True, f"Skill '{name}' installed to {dest_md}"

    def install_core_skills(self, names: list[str] | None = None) -> list[str]:
        """Install default onboarding skill set; returns list of installed names."""
        default = [
            "tell_joke",
            "repo_researcher",
            "write_release_notes",
            "telegram_setup",
            "daily_briefing",
            "summarize_meeting",
            "repo_onboard",
            "security_audit",
        ]
        installed: list[str] = []
        for name in names or default:
            ok, _ = self.install(name)
            if ok:
                installed.append(name)
            else:
                ok2, _ = self.install_bundled(name)
                if ok2:
                    self._mark_installed(name)
                    installed.append(name)
        return installed

    def uninstall(self, name: str) -> tuple[bool, str]:
        """Remove an installed skill or tool plugin by name."""
        from silex_core.utils.config import (
            KINTHIC_SKILLS,
            KINTHIC_PLUGINS_TOOLS,
            KINTHIC_PLUGINS_SKILLS,
        )

        catalog = self.load_catalog()
        entry = next((e for e in catalog if e.get("name") == name), None)
        if entry and entry.get("trust_level") == "core":
            return False, f"'{name}' is a core bundled plugin and cannot be removed."

        # Try flat skill
        skill_file = KINTHIC_SKILLS / f"{name}.md"
        if skill_file.exists():
            skill_file.unlink()
            self._mark_uninstalled(name)
            return True, f"Skill '{name}' removed."

        # Try nested skill folder
        for skill_dir in [KINTHIC_SKILLS / name, KINTHIC_PLUGINS_SKILLS / name]:
            if skill_dir.is_dir():
                shutil.rmtree(skill_dir)
                self._mark_uninstalled(name)
                return True, f"Skill '{name}' removed."

        # Try tool plugin folder
        tool_dir = KINTHIC_PLUGINS_TOOLS / name
        if tool_dir.is_dir():
            shutil.rmtree(tool_dir)
            self._mark_uninstalled(name)
            return True, f"Tool plugin '{name}' removed."

        return False, f"'{name}' not found in installed plugins or skills."

    @staticmethod
    def _download_bytes(url: str, max_bytes: int) -> bytes:
        """Download URL content with a hard size cap."""
        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"Download exceeds {max_bytes} bytes")
                chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _safe_extract_zip(zf, dest_dir) -> None:
        """Extract zip archive, rejecting path traversal (zip slip)."""
        from pathlib import Path

        dest_root = Path(dest_dir).resolve()
        for member in zf.namelist():
            target = (dest_root / member).resolve()
            if not str(target).startswith(str(dest_root)):
                raise ValueError(f"Unsafe zip entry: {member}")
        zf.extractall(dest_root)

    def _mark_installed(self, name: str) -> None:
        entries = self.load_catalog()
        for e in entries:
            if e.get("name") == name:
                e["installed"] = True
        self._write_catalog(entries)

    def _mark_uninstalled(self, name: str) -> None:
        entries = self.load_catalog()
        for e in entries:
            if e.get("name") == name:
                e["installed"] = False
        self._write_catalog(entries)

    # ------------------------------------------------------------------
    # Remote refresh
    # ------------------------------------------------------------------

    def refresh_from_remote(self, url: str | None = None) -> tuple[bool, str]:
        url = url or DEFAULT_REGISTRY_URL
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
                raw = resp.read().decode("utf-8")
            import yaml

            remote_data = yaml.safe_load(raw) or {}
            remote_entries: list[dict] = remote_data.get("entries", [])
        except Exception as exc:
            return False, f"Could not fetch remote registry: {exc}"

        local = self.load_catalog()
        local_names = {e.get("name") for e in local}
        added = 0
        for entry in remote_entries:
            if entry.get("name") not in local_names:
                entry.setdefault("installed", False)
                entry.setdefault("source", "remote")
                local.append(entry)
                added += 1

        self._write_catalog(local)
        return True, f"Registry refreshed: {added} new entries added from {url}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_all(self, type_filter: str | None = None) -> list[dict[str, Any]]:
        entries = self.load_catalog()
        if type_filter:
            return [e for e in entries if e.get("type") == type_filter]
        return entries

    def format_list(self, entries: list[dict]) -> str:
        if not entries:
            return "No results found."
        lines = []
        for e in entries:
            badge = {
                "core": "[core]",
                "verified": "[✓]",
                "community": "[community]",
            }.get(e.get("trust_level", "community"), "")
            installed = " (installed)" if e.get("installed") else ""
            lines.append(
                f"  {badge} {e.get('name')} ({e.get('type', '?')}) "
                f"v{e.get('version', '?')}{installed}"
            )
            if e.get("description"):
                lines.append(f"       {e['description'][:80]}")
        return "\n".join(lines)


# Module-level singleton
_registry: KinthicRegistry | None = None


def get_registry() -> KinthicRegistry:
    global _registry
    if _registry is None:
        _registry = KinthicRegistry()
    return _registry
