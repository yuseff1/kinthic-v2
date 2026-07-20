"""Skill management tools — progressive disclosure via skill_view."""

from __future__ import annotations

from typing import TYPE_CHECKING

from silex_core.tools.base import BaseTool

if TYPE_CHECKING:
    from silex_core.core.skills import SkillLoader


class SkillsListTool(BaseTool):
    name = "skills_list"
    description = "List available skills with compact descriptions and triggers."
    risk_level = "read_only"
    schema = {"type": "object", "properties": {}, "required": []}

    def __init__(self, skill_loader: SkillLoader | None = None) -> None:
        self.skill_loader = skill_loader

    async def execute(self, **kwargs) -> str:
        if not self.skill_loader:
            return "Error: skill loader not available."
        return self.skill_loader.format_index_text()


class SkillViewTool(BaseTool):
    name = "skill_view"
    description = "Load the full markdown instructions for a named skill."
    risk_level = "read_only"
    schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Skill name from the skills index",
            },
        },
        "required": ["name"],
    }

    def __init__(self, skill_loader: SkillLoader | None = None) -> None:
        self.skill_loader = skill_loader

    async def execute(self, **kwargs) -> str:
        name = str(kwargs.get("name", "")).strip()
        if not name:
            return "Error: name is required."
        if not self.skill_loader:
            return "Error: skill loader not available."
        body = self.skill_loader.get_skill_body(name)
        if body is None:
            known = ", ".join(sorted(self.skill_loader.skills.keys())[:20])
            return f"Error: skill '{name}' not found. Known skills: {known}"
        meta = self.skill_loader.skill_meta.get(name)
        header = f"# Skill: {name}\n"
        if meta and meta.trigger:
            header += f"Trigger: {meta.trigger}\n\n"
        return header + body


class SkillManageTool(BaseTool):
    name = "skill_manage"
    description = "Create or overwrite an agent skill in ~/.kinthic/skills/. Used for autonomous skill growth."
    risk_level = "repo_write"
    requires_approval = True
    schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the skill (e.g. data_pipeline)",
            },
            "content": {
                "type": "string",
                "description": "Full markdown content of the skill including YAML frontmatter.",
            },
        },
        "required": ["name", "content"],
    }

    def __init__(self, skill_loader: SkillLoader | None = None) -> None:
        self.skill_loader = skill_loader

    async def execute(self, **kwargs) -> str:
        name = str(kwargs.get("name", "")).strip()
        content = str(kwargs.get("content", "")).strip()

        if not name or not content:
            return "Error: name and content are required."

        import re
        from pathlib import Path
        from silex_core.utils.config import KINTHIC_SKILLS

        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name.lower())
        skills_dir = Path(KINTHIC_SKILLS)
        skills_dir.mkdir(parents=True, exist_ok=True)

        skill_path = skills_dir / f"{safe_name}.md"

        try:
            skill_path.write_text(content, encoding="utf-8")
            if self.skill_loader:
                self.skill_loader.reload()
            return f"Success: Skill {safe_name} written to {skill_path} and reloaded."
        except Exception as e:
            return f"Error writing skill: {e}"
