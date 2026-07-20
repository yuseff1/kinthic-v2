import shutil, re
from pathlib import Path
import os

MAPPING = {
    "from silex.utils.config import SILEX_DB, SILEX_VECTOR_DB": "from silex_engine.config import SILEX_DB, SILEX_VECTOR_DB",
    "from silex.utils.config": "from silex_engine.config",
    "from silex.world.": "from silex_engine.world.",
    "from silex.memory.memory_store": "from silex_engine.memory.memory_store",
    "from silex.memory.admission_control": "from silex_engine.memory.admission_control",
    "from silex.memory.vector_store": "from silex_engine.memory.vector_store",
    "from silex.storage.": "from silex_engine.storage.",
    "from silex.knowledge_graph.": "from silex_engine.knowledge_graph.",
    "from silex.models.schemas": "from silex_engine.models.schemas",
    "from silex.mcp.server": "from silex_engine.mcp.server",
    "from silex.core.causal_graph": "from silex_engine.world.causal_graph"
}

def migrate_file(src: Path, dst: Path):
    if not src.exists():
        print(f"Skipping {src} (does not exist)")
        return
    content = src.read_text(encoding="utf-8")
    for old, new in MAPPING.items():
        content = content.replace(old, new)
    # Flag any remaining silex. imports
    remaining = [line for line in content.splitlines() if "from silex." in line or "import silex." in line]
    if remaining:
        print(f"[WARNING] {dst.name}: {len(remaining)} unmapped imports:")
        for line in remaining:
            print(f"   {line.strip()}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content, encoding="utf-8")
    print(f"Migrated {src.name} to {dst}")

def main():
    src_base = Path("E:/AGI/silex")
    dst_base = Path("d:/varsen/kinthic/silex_engine")
    
    files_to_migrate = [
        (src_base / "world" / "graph.py", dst_base / "world" / "graph.py"),
        (src_base / "world" / "belief_engine.py", dst_base / "world" / "belief_engine.py"),
        (src_base / "world" / "contradictions.py", dst_base / "world" / "contradictions.py"),
        (src_base / "world" / "hypotheses.py", dst_base / "world" / "hypotheses.py"),
        (src_base / "core" / "causal_graph.py", dst_base / "world" / "causal_graph.py"),
        (src_base / "memory" / "memory_store.py", dst_base / "memory" / "memory_store.py"),
        (src_base / "memory" / "admission_control.py", dst_base / "memory" / "admission_control.py"),
        (src_base / "memory" / "vector_store.py", dst_base / "memory" / "vector_store.py"),
        (src_base / "storage" / "database.py", dst_base / "storage" / "database.py"),
        (src_base / "storage" / "graph_buffer.py", dst_base / "storage" / "graph_buffer.py"),
        (src_base / "knowledge_graph" / "ontology.py", dst_base / "knowledge_graph" / "ontology.py"),
        (src_base / "knowledge_graph" / "mapper.py", dst_base / "knowledge_graph" / "mapper.py"),
        (src_base / "models" / "schemas.py", dst_base / "models" / "schemas.py"),
    ]
    
    # MCP Server directory
    mcp_src = src_base / "mcp" / "server"
    if mcp_src.exists():
        for root, _, files in os.walk(mcp_src):
            for file in files:
                if file.endswith(".py"):
                    rel_path = Path(root).relative_to(mcp_src)
                    src_file = Path(root) / file
                    dst_file = dst_base / "mcp" / "server" / rel_path / file
                    files_to_migrate.append((src_file, dst_file))
                    
    for src, dst in files_to_migrate:
        migrate_file(src, dst)
        
    print("Migration complete.")

if __name__ == "__main__":
    main()
