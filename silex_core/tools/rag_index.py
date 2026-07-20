"""
silex/tools/rag_index.py — RAG indexing tool for the LLM.

Allows KINTHIC to index files or folders into ChromaDB autonomously.
"""

from __future__ import annotations
from pathlib import Path
from silex_core.tools.base import BaseTool
from silex_core.utils.config import WORKSPACE_DIR


def _is_path_allowed(path: Path) -> bool:
    import sys, re
    # Resolve and translate Windows path format on WSL/Linux
    path_str = str(path)
    if sys.platform != "win32":
        match = re.match(r"^([a-zA-Z]):[/\\](.*)", path_str)
        if match:
            drive = match.group(1).lower()
            rest = match.group(2).replace("\\", "/")
            path_str = f"/mnt/{drive}/{rest}"
    path = Path(path_str)
    if sys.platform != "win32":
        import os
        path_str = os.path.normpath(str(path))
        parts = path_str.split(os.sep)
        current_path = parts[0] if parts[0] else os.sep
        for part in parts[1:]:
            if os.path.exists(current_path):
                try:
                    files = os.listdir(current_path)
                    for f in files:
                        if f.lower() == part.lower():
                            current_path = os.path.join(current_path, f)
                            break
                    else:
                        current_path = os.path.join(current_path, part)
                except Exception:
                    current_path = os.path.join(current_path, part)
            else:
                current_path = os.path.join(current_path, part)
        path = Path(current_path)

    # 1. Allowed in workspace
    try:
        path.resolve().relative_to(WORKSPACE_DIR.resolve())
        return True
    except ValueError:
        pass

    # 2. Allowed in second-brain
    try:
        sb_path = Path("D:/second-brain" if sys.platform == "win32" else "/mnt/d/second-brain").resolve(strict=False)
        path.resolve().relative_to(sb_path)
        return True
    except ValueError:
        pass
    except Exception:
        pass

    return False


class RAGIndexTool(BaseTool):
    name = "rag_index"
    description = (
        "Index a local file or directory into the knowledge base so it can be "
        "semantically queried via rag_query. Use when the user asks you to save, "
        "store, index, or remember a document, article, or directory."
    )
    risk_level = "read_only"
    requires_approval = False
    schema = {
        "path": "string (absolute or relative path to the file or directory to index)",
    }

    def __init__(self, file_indexer=None):
        self._indexer = file_indexer

    async def execute(self, **kwargs) -> str:
        path_str = kwargs.get("path")
        if not path_str:
            return "Error: 'path' argument is required."

        # Translate Windows-style paths on Linux/WSL
        import sys, re
        if sys.platform != "win32":
            match = re.match(r"^([a-zA-Z]):[/\\](.*)", path_str)
            if match:
                drive = match.group(1).lower()
                rest = match.group(2).replace("\\", "/")
                path_str = f"/mnt/{drive}/{rest}"
            
            # Resolve case-insensitively on Linux/WSL
            import os
            path_str = os.path.normpath(path_str)
            parts = path_str.split(os.sep)
            current_path = parts[0] if parts[0] else os.sep
            for part in parts[1:]:
                if os.path.exists(current_path):
                    try:
                        files = os.listdir(current_path)
                        for f in files:
                            if f.lower() == part.lower():
                                current_path = os.path.join(current_path, f)
                                break
                        else:
                            current_path = os.path.join(current_path, part)
                    except Exception:
                        current_path = os.path.join(current_path, part)
                else:
                    current_path = os.path.join(current_path, part)
            path_str = current_path

        path = Path(path_str)
        # If relative, resolve against workspace
        if not path.is_absolute():
            path = WORKSPACE_DIR / path

        try:
            resolved_path = path.resolve()
        except Exception as e:
            return f"Error: Failed to resolve path '{path_str}': {e}"

        if not _is_path_allowed(resolved_path):
            return f"Error: Access denied — path is outside authorized directories."

        if not self._indexer:
            return "Error: File indexer is not initialized."

        try:
            import anyio.to_thread

            if resolved_path.is_dir():
                stats = await anyio.to_thread.run_sync(
                    self._indexer.index_folder, resolved_path
                )
                return f"Successfully indexed folder: {stats['indexed']} files indexed ({stats['skipped']} unchanged, {stats['errors']} errors)."
            elif resolved_path.is_file():
                chunks = await anyio.to_thread.run_sync(
                    self._indexer.index_file, resolved_path
                )
                return f"Successfully indexed file '{resolved_path.name}' ({chunks} chunks created/updated)."
            else:
                return f"Error: Path '{resolved_path}' is neither a file nor a directory."
        except Exception as e:
            return f"Error occurred during indexing: {e}"
