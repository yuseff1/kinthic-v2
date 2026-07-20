from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from silex_engine.memory.vector_store import VectorStore

from silex_core.utils.logger import setup_logger
from silex_core.utils.config import KINTHIC_SKILLS, KINTHIC_PLUGINS_SKILLS, KINTHIC_HOME

log = setup_logger("kinthic.skills")

# Filenames excluded from loading as executable skills (contributor docs, etc.).
_SKIP_SKILL_NAMES = frozenset({"readme", "plugin_development"})


class SkillMeta:
    """Lightweight metadata record for a loaded skill."""

    __slots__ = (
        "name",
        "source_path",
        "description",
        "version",
        "author",
        "tags",
        "trust_level",
        "trigger",
        "inline",
        "source",
    )

    def __init__(
        self,
        name: str,
        source_path: Path,
        description: str = "",
        version: str = "1.0.0",
        author: str = "community",
        tags: list[str] | None = None,
        trust_level: str = "community",
        trigger: str = "",
        inline: bool = False,
        source: str = "",
    ) -> None:
        self.name = name
        self.source_path = source_path
        self.description = description
        self.version = version
        self.author = author
        self.tags = tags or []
        self.trust_level = trust_level  # core | verified | community
        self.trigger = trigger
        self.inline = inline
        self.source = source  # bundled | genesis | evolution | user | community


class SkillLoader:
    """
    Loads Markdown skill files from multiple source directories:

      ~/.kinthic/skills/           — flat *.md files (original user-managed location)
      ~/.kinthic/skills/<dir>/     — nested: looks for SKILL.md inside sub-directories
      ~/.kinthic/plugins/skills/   — community plugin skills (each folder = one skill)

    Each skill may optionally ship a skill.yaml alongside its SKILL.md with metadata:
      name, description, version, author, tags, trust_level, trigger, signature

    Signature validation is applied to community plugins (trust_level: community).
    Signed skills from verified publishers carry trust_level: verified.
    """

    def __init__(self, vector_store: VectorStore | None = None):
        self.skills_dir = KINTHIC_SKILLS
        self.plugins_skills_dir = KINTHIC_PLUGINS_SKILLS
        self.skills: dict[str, str] = {}  # name → markdown content
        self.skill_meta: dict[str, SkillMeta] = {}  # name → metadata
        self.vector_store = vector_store
        self.collection = None

        if self.vector_store and self.vector_store.is_active:
            try:
                self.collection = self.vector_store.client.get_or_create_collection(
                    name="kinthic_skills",
                    embedding_function=self.vector_store.embedding_function,
                )
            except Exception as e:
                log.warning(f"Could not initialize vector collection for skills: {e}")

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_all(self) -> int:
        """Scan all skill source directories and load every Markdown skill."""
        self.skills.clear()
        self.skill_meta.clear()

        sources: list[tuple[Path, str]] = []  # (md_file, trust_level)

        # 1. Flat files in ~/.kinthic/skills/*.md (user-managed; trust from frontmatter/sidecar)
        if self.skills_dir.exists():
            try:
                for fp in sorted(self.skills_dir.glob("*.md")):
                    if fp.stem.lower() not in _SKIP_SKILL_NAMES:
                        sources.append((fp, "community"))
            except Exception as e:
                log.warning(f"Could not scan flat skills directory: {e}")

        # 2. Nested folders in ~/.kinthic/skills/<name>/SKILL.md
        if self.skills_dir.exists():
            try:
                for sub in sorted(self.skills_dir.iterdir()):
                    if sub.is_dir() and not sub.name.startswith((".", "_")):
                        skill_md = sub / "SKILL.md"
                        if not skill_md.exists():
                            skill_md = next(sub.glob("*.md"), None)  # type: ignore[arg-type]
                        if skill_md and skill_md.stem.lower() not in _SKIP_SKILL_NAMES:
                            sources.append((skill_md, "community"))
            except Exception as e:
                log.warning(f"Could not scan nested skills directory: {e}")

        # 3. Community plugin skills in ~/.kinthic/plugins/skills/<name>/
        if self.plugins_skills_dir.exists():
            try:
                for plugin_dir in sorted(self.plugins_skills_dir.iterdir()):
                    if plugin_dir.is_dir() and not plugin_dir.name.startswith((".", "_")):
                        skill_md = plugin_dir / "SKILL.md"
                        if not skill_md.exists():
                            skill_md = next(plugin_dir.glob("*.md"), None)  # type: ignore[arg-type]
                        if skill_md and skill_md.stem.lower() not in _SKIP_SKILL_NAMES:
                            trust = self._resolve_trust(plugin_dir)
                            sources.append((skill_md, trust))
            except Exception as e:
                log.warning(f"Could not scan plugin skills directory: {e}")

        # 4. Workspace-scoped skills in WORKSPACE_DIR / ".agents" / "skills" and PROJECT_ROOT / ".agents" / "skills"
        from silex_core.utils.config import WORKSPACE_DIR, PROJECT_ROOT
        for root in sorted({WORKSPACE_DIR, PROJECT_ROOT}):
            workspace_skills_dir = root / ".agents" / "skills"
            if workspace_skills_dir.exists():
                try:
                    for sub in sorted(workspace_skills_dir.iterdir()):
                        if sub.is_dir() and not sub.name.startswith((".", "_")):
                            skill_md = sub / "SKILL.md"
                            if not skill_md.exists():
                                skill_md = next(sub.glob("*.md"), None)  # type: ignore[arg-type]
                            if skill_md and skill_md.stem.lower() not in _SKIP_SKILL_NAMES:
                                sources.append((skill_md, "community"))
                except Exception as e:
                    log.warning(f"Could not scan workspace skills directory at {root}: {e}")

        count = 0
        seen_names: set[str] = set()

        for file_path, default_trust in sources:
            # Derive skill name: folder name for nested, stem for flat
            if file_path.parent != self.skills_dir:
                skill_name = file_path.parent.name
            else:
                skill_name = file_path.stem

            if skill_name in seen_names:
                continue  # later-loaded dirs shadow earlier
            seen_names.add(skill_name)

            try:
                raw_content = file_path.read_text(encoding="utf-8")
                frontmatter, body = self._parse_frontmatter(raw_content)
                meta = self._load_meta(
                    file_path, skill_name, default_trust, frontmatter
                )

                self.skills[skill_name] = (
                    body.strip() if body.strip() else raw_content.strip()
                )
                self.skill_meta[skill_name] = meta
                count += 1

                if self.collection:
                    self.collection.upsert(
                        documents=[self.skills[skill_name]],
                        metadatas=[
                            {
                                "name": skill_name,
                                "trust_level": meta.trust_level,
                                "tags": ",".join(meta.tags),
                            }
                        ],
                        ids=[f"skill_{skill_name}"],
                    )
            except Exception as e:
                log.error("Failed to load skill %s: %s", skill_name, e)

        log.info(
            "Loaded %d skills (%d flat, %d nested/plugin)",
            count,
            sum(1 for s in self.skill_meta.values() if s.trust_level == "core"),
            sum(1 for s in self.skill_meta.values() if s.trust_level != "core"),
        )
        return count

    def reload(self) -> int:
        """Alias for load_all() — used by skill_manage and hot-reload callers."""
        return self.load_all()

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_frontmatter(content: str) -> tuple[dict, str]:
        """Parse agentskills.io-style YAML frontmatter from markdown."""
        if not content.startswith("---"):
            return {}, content
        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}, content
        try:
            import yaml

            frontmatter = yaml.safe_load(parts[1]) or {}
            if not isinstance(frontmatter, dict):
                frontmatter = {}
            body = parts[2].lstrip("\n")
            return frontmatter, body
        except Exception:
            return {}, content

    def _yaml_sidecar_paths(self, md_path: Path, skill_name: str) -> list[Path]:
        """Candidate skill.yaml sidecar paths for flat or nested layouts."""
        return [
            md_path.parent / "skill.yaml",
            md_path.with_suffix(".yaml"),
            md_path.parent / f"{skill_name}.yaml",
        ]

    def _load_meta(
        self,
        md_path: Path,
        skill_name: str,
        default_trust: str,
        frontmatter: dict | None = None,
    ) -> SkillMeta:
        """Parse optional skill.yaml alongside the SKILL.md and YAML frontmatter."""
        manifest: dict = dict(frontmatter or {})
        for yaml_path in self._yaml_sidecar_paths(md_path, skill_name):
            if yaml_path.exists():
                try:
                    import yaml

                    with open(yaml_path, encoding="utf-8") as f:
                        sidecar = yaml.safe_load(f) or {}
                    if isinstance(sidecar, dict):
                        manifest = {**sidecar, **manifest}
                except Exception as exc:
                    log.debug(
                        "Could not parse %s for %s: %s", yaml_path.name, skill_name, exc
                    )
                break

        metadata = manifest.get("metadata") or {}
        if isinstance(metadata, dict):
            if not manifest.get("trigger") and metadata.get("trigger"):
                manifest["trigger"] = metadata["trigger"]
            if "inline" not in manifest and metadata.get("inline") is not None:
                manifest["inline"] = metadata["inline"]

        description = str(manifest.get("description", ""))
        if not description:
            for line in md_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip().lstrip("#").strip()
                if stripped and not stripped.startswith("---"):
                    description = stripped
                    break

        inline_val = manifest.get("inline", False)
        if isinstance(inline_val, str):
            inline_val = inline_val.lower() in ("true", "1", "yes")

        declared_source = str(manifest.get("source", "")).strip()
        meta = SkillMeta(
            name=str(manifest.get("name", skill_name)),
            source_path=md_path,
            description=description[:120],
            version=str(manifest.get("version", "1.0.0")),
            author=str(manifest.get("author", "community")),
            tags=list(manifest.get("tags", [])),
            trust_level=str(manifest.get("trust_level", default_trust)),
            trigger=str(manifest.get("trigger", "")),
            inline=bool(inline_val),
            source=declared_source,
        )
        if not meta.source:
            meta.source = self._infer_source(meta)
        return meta

    def _infer_layout(self, meta: SkillMeta) -> str:
        path = meta.source_path
        parts = path.parts
        if "plugins" in parts and "skills" in parts:
            return "plugin"
        if path.name.upper() == "SKILL.MD" or path.parent != self.skills_dir:
            return "nested"
        return "flat"

    def _infer_source(self, meta: SkillMeta) -> str:
        if "bundled" in meta.tags or (
            meta.trust_level == "core" and meta.author.lower() == "openyf"
        ):
            return "bundled"
        author = meta.author.lower()
        if author in ("genesis", "evolution"):
            return author
        parts = meta.source_path.parts
        if "plugins" in parts and "skills" in parts:
            return "community"
        if meta.source_path.parent == self.skills_dir:
            return "user"
        return "user"

    def _resolve_trust(self, plugin_dir: Path) -> str:
        """Determine trust level for a plugin-skills folder; validate HMAC if signed."""
        yaml_path = plugin_dir / "skill.yaml"
        if not yaml_path.exists():
            return "community"
        try:
            import yaml

            with open(yaml_path, encoding="utf-8") as f:
                manifest = yaml.safe_load(f) or {}
        except Exception:
            return "community"

        trust = str(manifest.get("trust_level", "community"))
        signature = manifest.get("signature", "")
        if not signature:
            return "community"

        # Verify HMAC-SHA256 using the local HMAC key (if present)
        hmac_key_path = KINTHIC_HOME / "config" / "hmac_key.bin"
        if hmac_key_path.exists():
            try:
                key = hmac_key_path.read_bytes()
                skill_md = plugin_dir / "SKILL.md"
                if not skill_md.exists():
                    skill_md = next(plugin_dir.glob("*.md"), None)
                if skill_md:
                    content = skill_md.read_bytes()
                    expected = hmac.new(key, content, hashlib.sha256).hexdigest()
                    if hmac.compare_digest(expected, signature):
                        return "verified"
                    log.warning(
                        "Skill %s has an invalid HMAC signature — treating as community",
                        plugin_dir.name,
                    )
                    return "community"
            except Exception as exc:
                log.debug("Signature check failed for %s: %s", plugin_dir.name, exc)

        return trust

    def get_relevant_skills(self, query: str, limit: int = 3) -> dict[str, str]:
        """Retrieve only the top matches relevant to the user query."""
        if not self.skills:
            return {}

        if not self.collection:
            return dict(list(self.skills.items())[:limit])

        try:
            results = self.collection.query(
                query_texts=[query], n_results=min(limit, len(self.skills))
            )

            relevant = {}
            if results and results.get("metadatas") and results["metadatas"][0]:
                for meta in results["metadatas"][0]:
                    name = meta.get("name")
                    if name and name in self.skills:
                        relevant[name] = self.skills[name]
            return relevant
        except Exception as e:
            log.error(f"Error querying semantic skills: {e}")
            return dict(list(self.skills.items())[:limit])

    def format_index_for_prompt(self) -> str:
        """Compact skill index for system prompt (progressive disclosure)."""
        if not self.skill_meta:
            return ""

        badge_map = {"core": "[core]", "verified": "[✓]", "community": "[community]"}
        lines = [
            "═══════════════════════════════════════════════════════════",
            "SKILLS INDEX (use skill_view tool to load full instructions)",
            "═══════════════════════════════════════════════════════════",
        ]
        for name, meta in sorted(self.skill_meta.items(), key=lambda x: x[0]):
            badge = badge_map.get(meta.trust_level, "")
            trigger = f' trigger="{meta.trigger}"' if meta.trigger else ""
            inline_note = " [inline]" if meta.inline else ""
            lines.append(
                f"- {badge} **{name}**{inline_note}: {meta.description}{trigger}"
            )
        lines.append("")
        lines.append(
            "Call skill_view(name) when a workflow matches the user's request."
        )
        return "\n".join(lines)

    def format_inline_skills(self, query: str | None = None) -> str:
        """Inject full body only for skills marked inline: true."""
        inline_names = [n for n, m in self.skill_meta.items() if m.inline]
        if not inline_names:
            return ""

        if query:
            relevant = set(
                self.get_relevant_skills(query, limit=len(inline_names)).keys()
            )
            inline_names = [n for n in inline_names if n in relevant] or inline_names[
                :2
            ]

        sections = ["INLINE SKILLS (full instructions):"]
        for name in inline_names:
            content = self.skills.get(name, "")
            if content:
                sections.append(f'<skill name="{name}">')
                sections.append(content.strip())
                sections.append("</skill>\n")
        return "\n".join(sections) if len(sections) > 1 else ""

    def format_for_prompt(self, query: str | None = None) -> str:
        """Format skills for system prompt: index + optional inline bodies."""
        index = self.format_index_for_prompt()
        inline = self.format_inline_skills(query)
        if index and inline:
            return f"{index}\n\n{inline}"
        return index or inline

    def get_skill_body(self, name: str) -> str | None:
        """Return full skill markdown body by name."""
        return self.skills.get(name)

    def format_index_text(self) -> str:
        """Plain-text index for skills_list tool."""
        if not self.skill_meta:
            return "No skills loaded."
        rows = []
        for name, meta in sorted(self.skill_meta.items(), key=lambda x: x[0]):
            rows.append(
                f"{name} ({meta.trust_level}): {meta.description}"
                + (f" | trigger: {meta.trigger}" if meta.trigger else "")
            )
        return "\n".join(rows)

    def list_skills(self) -> list[dict]:
        """Return a list of loaded skill metadata dicts for the :skills command."""
        return self.list_skills_detailed()

    def list_skills_detailed(self) -> list[dict]:
        """Return loaded skill metadata for API, CLI, and Telegram surfaces."""
        rows = []
        for name, meta in self.skill_meta.items():
            try:
                size_bytes = meta.source_path.stat().st_size
            except OSError:
                size_bytes = len(self.skills.get(name, ""))
            rows.append(
                {
                    "name": name,
                    "description": meta.description,
                    "version": meta.version,
                    "author": meta.author,
                    "tags": meta.tags,
                    "trust_level": meta.trust_level,
                    "trigger": meta.trigger,
                    "source": meta.source,
                    "layout": self._infer_layout(meta),
                    "source_path": str(meta.source_path),
                    "size_bytes": size_bytes,
                }
            )
        rows.sort(key=lambda r: (r["trust_level"] != "core", r["name"]))
        return rows
