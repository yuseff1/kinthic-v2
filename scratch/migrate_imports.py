import shutil, re
from pathlib import Path

MAPPING = {
    "from silex.utils.config": "from silex_core.utils.config",
    "from silex.utils.logger": "from silex_core.utils.logger",
    "from silex.utils.tasks": "from silex_core.utils.tasks",
    "from silex.world.": "from silex_engine.world.",
    "from silex.memory.memory_store": "from silex_engine.memory.memory_store",
    "from silex.memory.admission_control": "from silex_engine.memory.admission_control",
    "from silex.memory.vector_store": "from silex_engine.memory.vector_store",
    "from silex.storage.": "from silex_engine.storage.",
    "from silex.tools.": "from silex_core.tools.",
    "from silex.llm.": "from silex_core.llm.",
    "from silex.adapters.": "from silex_core.adapters.",
    "from silex.security.": "from silex_core.security.",
    "from silex.ui.": "from silex_core.ui.",
    "from silex.runtime.": "from silex_core.runtime.",
    "from silex.plugins.": "from silex_core.plugins.",
    "from silex.mcp.": "from silex_core.mcp.",
    "from silex.api.": "from silex_core.api.",
    # Deleted modules — flag, don't replace
    "from silex.core.cognitive_loop": "# MIGRATION: cognitive_loop deleted — use silex_core.loop.AgentLoop",
    "from silex.core.context_builder": "# MIGRATION: context_builder deleted — use silex_core.harness.context_builder",
    
    # Catch-all for others mapped to silex_core
    "from silex.": "from silex_core.",
    "import silex.": "import silex_core."
}

def migrate_directory(directory: Path):
    for filepath in directory.rglob("*.py"):
        content = filepath.read_text(encoding="utf-8")
        original_content = content
        
        for old, new in MAPPING.items():
            content = content.replace(old, new)
            
        if content != original_content:
            filepath.write_text(content, encoding="utf-8")
            print(f"Migrated imports in: {filepath}")

if __name__ == "__main__":
    base_dir = Path("d:/varsen/kinthic/silex_core")
    migrate_directory(base_dir / "tools")
    migrate_directory(base_dir / "llm")
    migrate_directory(base_dir / "mcp")
    migrate_directory(base_dir / "memory")
    migrate_directory(base_dir / "skills")
    migrate_directory(base_dir / "runtime")
    
    # Week 8
    migrate_directory(base_dir / "adapters")
    migrate_directory(base_dir / "ui")
    migrate_directory(base_dir / "security")
    migrate_directory(base_dir / "api")
    migrate_directory(Path("d:/varsen/kinthic/scripts"))
    
    # Process standalone files in root
    obs = base_dir / "observability.py"
    if obs.exists():
        content = obs.read_text(encoding="utf-8")
        original_content = content
        for old, new in MAPPING.items():
            content = content.replace(old, new)
        if content != original_content:
            obs.write_text(content, encoding="utf-8")
            print(f"Migrated imports in: {obs}")
            
    print("Migration script completed.")
