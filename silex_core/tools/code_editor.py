"""
Code Editor Tool — allows KINTHIC to propose and apply file changes.

Security (v1.0.5):
  - All paths are sandboxed to KINTHIC_WORKSPACE (not the repo root).
  - The autonomous apply bypass has been removed. ALL edits flow through
    the approval queue in the ToolRegistry.
  - The code-apply operator flag now controls whether the registry
    auto-approves code edits.
  - Dotfiles and sensitive directories are always blocked.
"""

import json
import uuid
from pathlib import Path

from silex_core.tools.base import BaseTool
from silex_core.utils.logger import setup_logger
from silex_core.utils.config import KINTHIC_PENDING_EDITS

log = setup_logger("silex.tools.code_editor")

# ---------------------------------------------------------------------------
# Security — sandbox boundary (matches file_reader.py)
# ---------------------------------------------------------------------------

# Sandbox root: resolved from config.py (KINTHIC_WORKSPACE or env override).
# This ensures pip-installed copies don't accidentally write to site-packages.
from silex_core.utils.config import WORKSPACE_DIR as _WORKSPACE_ROOT  # noqa: E402

PENDING_EDITS_FILE = KINTHIC_PENDING_EDITS
BLOCKED_FILE_PREFIXES = (".env",)
BLOCKED_PATH_PARTS = {".git", "node_modules", ".venv", "venv", "__pycache__"}


def _resolve_workspace_path(file_path: str) -> Path:
    """Resolve a user-supplied path inside the KINTHIC workspace sandbox.

    Security guarantees:
      1. The resolved path must be inside _WORKSPACE_ROOT or the second-brain directory.
      2. Dotfiles (.env*) are always blocked.
      3. Sensitive directories (.git, node_modules, etc.) are blocked.
    """
    import sys, re
    path_str = str(file_path)
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
    candidate = Path(path_str)

    is_sb = False
    try:
        if candidate.is_absolute():
            sb_path = Path("D:/second-brain" if sys.platform == "win32" else "/mnt/d/second-brain").resolve(strict=False)
            try:
                candidate.resolve().relative_to(sb_path)
                is_sb = True
            except ValueError:
                pass
    except Exception:
        pass

    if not is_sb and not candidate.is_absolute():
        candidate = _WORKSPACE_ROOT / candidate
    full_path = candidate.resolve()

    try:
        full_path.relative_to(_WORKSPACE_ROOT)
    except ValueError:
        try:
            sb_path = Path("D:/second-brain" if sys.platform == "win32" else "/mnt/d/second-brain").resolve(strict=False)
            full_path.relative_to(sb_path)
            is_sb = True
        except ValueError:
            pass
        except Exception:
            pass
        if not is_sb:
            raise ValueError(
                f"Access denied — path is outside the workspace directory ({_WORKSPACE_ROOT.name}/)."
            )

    if full_path.name.startswith(BLOCKED_FILE_PREFIXES):
        raise ValueError("Access denied — environment files are restricted.")
    if any(part in BLOCKED_PATH_PARTS for part in full_path.parts):
        raise ValueError("Access denied — restricted directory component.")

    return full_path


class CodeEditorTool(BaseTool):
    """
    Allows KINTHIC to propose changes to files in the workspace.

    Security: This tool NEVER applies edits directly. It always creates
    a draft proposal. The ToolRegistry's approval queue
    decides whether and when the edit is actually applied.
    """

    name = "propose_code_edit"
    risk_level = "repo_write"
    requires_approval = True
    description = (
        "Propose a change to a file in the workspace or the second-brain directory (D:/second-brain/). "
        "The change will NOT be applied immediately — it will be saved as a draft pending human approval. "
        "Ask the user to approve the edit in your response."
    )

    schema = {
        "file_path": "string (relative path to the file inside the workspace, or absolute path inside the second-brain directory)",
        "target_content": "string (the exact block of code to replace. Leave empty to overwrite the entire file or write a new file)",
        "replacement_content": "string (the new code or text content to insert)",
        "explanation": "string (why you are making this change)",
    }

    async def execute(self, **kwargs) -> str:
        file_path = kwargs.get("file_path")
        target_content = kwargs.get("target_content", "")
        replacement_content = kwargs.get("replacement_content", "")
        explanation = kwargs.get("explanation", "No explanation provided.")

        if not file_path or not replacement_content:
            return "ERROR: file_path and replacement_content are required."

        try:
            full_path = _resolve_workspace_path(file_path)
        except ValueError as e:
            return f"ERROR: {e}"

        # Verify target content if provided
        if target_content and full_path.exists():
            with open(full_path, "r", encoding="utf-8") as f:
                current_code = f.read()
                if target_content not in current_code:
                    return "ERROR: The target_content was not found exactly as written in the file."
                if current_code.count(target_content) != 1:
                    return "ERROR: The target_content is ambiguous. It appears multiple times in the file. Please provide a larger, unique block of code to replace."

        # Load existing pending edits
        pending_edits = []
        if PENDING_EDITS_FILE.exists():
            try:
                with open(PENDING_EDITS_FILE, "r", encoding="utf-8") as f:
                    pending_edits = json.load(f)
                    if not isinstance(pending_edits, list):
                        pending_edits = []
            except (json.JSONDecodeError, OSError, ValueError):
                pending_edits = []

        proposal = {
            "id": str(uuid.uuid4())[:8],
            "file_path": str(full_path),
            "target_content": target_content,
            "replacement_content": replacement_content,
            "explanation": explanation,
            "status": "pending",
        }

        # ALL edits go to the pending queue. The approval
        # flow in the ToolRegistry decide when they are applied.
        # The operator's code-apply flag is handled by the registry's
        # _approval_required() method, NOT here.
        pending_edits.append(proposal)
        with open(PENDING_EDITS_FILE, "w", encoding="utf-8") as f:
            json.dump(pending_edits, f, indent=4)

        return (
            f"DRAFT CREATED (ID: {proposal['id']}) for {file_path}.\n"
            f"STATUS: PENDING HUMAN APPROVAL.\n"
            f"INSTRUCTION: Ask the user to 'approve edit {proposal['id']}' or 'approve all edits'."
        )

    def _apply_edit_logic(self, proposal: dict):
        """Apply a single edit proposal to disk.

        Called ONLY by ApplyEditTool after the edit has passed through
        the approval queue.
        """
        import shutil
        from datetime import datetime
        from silex_core.utils.config import KINTHIC_BACKUPS

        full_path = _resolve_workspace_path(proposal["file_path"])
        full_path.parent.mkdir(parents=True, exist_ok=True)

        if full_path.exists():
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = KINTHIC_BACKUPS / f"{full_path.name}_{timestamp}.bak"
                shutil.copy2(full_path, backup_path)
                log.info(f"Failsafe backup created: {backup_path}")
            except Exception as e:
                log.warning(f"Failed to create failsafe backup for {full_path}: {e}")

        if proposal["target_content"] and full_path.exists():
            with open(full_path, "r", encoding="utf-8") as f:
                current_code = f.read()
            new_code = current_code.replace(
                proposal["target_content"], proposal["replacement_content"], 1
            )
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_code)
        else:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(proposal["replacement_content"])


class ApplyEditTool(BaseTool):
    """
    Applies pending code edits that have been approved.
    """

    name = "apply_approved_edit"
    risk_level = "repo_write"
    requires_approval = True
    description = (
        "Applies one or all pending code edits. "
        "Usage: Provide 'edit_id' for a specific file, or leave empty to apply ALL pending edits."
    )

    schema = {
        "edit_id": "string (optional, the ID of a specific edit to apply. If omitted, all edits are applied)"
    }

    async def execute(self, **kwargs) -> str:
        edit_id = kwargs.get("edit_id")

        if not PENDING_EDITS_FILE.exists():
            return "ERROR: No pending edits found."

        try:
            with open(PENDING_EDITS_FILE, "r", encoding="utf-8") as f:
                pending = json.load(f)

            if not pending:
                return "ERROR: No pending edits in the list."

            if edit_id:
                # Apply specific edit
                to_apply = [e for e in pending if e["id"] == edit_id]
                if not to_apply:
                    return f"ERROR: No edit found with ID {edit_id}."

                edit = to_apply[0]

                # Enforce strict runtime approval rule
                if edit.get("status") != "approved":
                    # Try manual operator key challenge via CLI terminal shell
                    import sys
                    import random

                    if sys.stdin.isatty():
                        challenge = str(random.randint(1000, 9999))
                        print(
                            f"\n[SECURITY] OPERATOR KEY CHALLENGE REQUIRED TO APPROVE EDIT {edit_id}"
                        )
                        print(
                            f"Please type the following challenge code to confirm: {challenge}"
                        )
                        try:
                            user_input = input("Enter code: ").strip()
                            if user_input == challenge:
                                print("[SECURITY] Challenge successful. Edit approved.")
                                edit["status"] = "approved"
                                # Update pending edits file with the approved status
                                with open(
                                    PENDING_EDITS_FILE, "w", encoding="utf-8"
                                ) as f:
                                    json.dump(pending, f, indent=4)
                            else:
                                return (
                                    "ERROR: Operator challenge failed. Edit rejected."
                                )
                        except Exception as e:
                            return f"ERROR during operator challenge: {e}"
                    else:
                        return "ERROR: Edit has not been approved by operator (requires manual CLI challenge or internal system event)."

                CodeEditorTool()._apply_edit_logic(edit)

                # Remove from list
                remaining = [e for e in pending if e["id"] != edit_id]
                if remaining:
                    with open(PENDING_EDITS_FILE, "w", encoding="utf-8") as f:
                        json.dump(remaining, f, indent=4)
                else:
                    PENDING_EDITS_FILE.unlink()

                return f"SUCCESS: Edit {edit_id} for {Path(edit['file_path']).name} applied."

            else:
                # Apply ALL
                # First, ensure all pending edits are approved
                for edit in pending:
                    if edit.get("status") != "approved":
                        import sys
                        import random

                        if sys.stdin.isatty():
                            challenge = str(random.randint(1000, 9999))
                            print(
                                "\n[SECURITY] OPERATOR KEY CHALLENGE REQUIRED TO APPROVE ALL PENDING EDITS"
                            )
                            print(
                                f"Please type the following challenge code to confirm: {challenge}"
                            )
                            try:
                                user_input = input("Enter code: ").strip()
                                if user_input == challenge:
                                    print(
                                        "[SECURITY] Challenge successful. All edits approved."
                                    )
                                    for e in pending:
                                        e["status"] = "approved"
                                    with open(
                                        PENDING_EDITS_FILE, "w", encoding="utf-8"
                                    ) as f:
                                        json.dump(pending, f, indent=4)
                                    break
                                else:
                                    return "ERROR: Operator challenge failed. Edits rejected."
                            except Exception as e:
                                return f"ERROR during operator challenge: {e}"
                        else:
                            return "ERROR: Some pending edits have not been approved by operator (requires manual CLI challenge or internal system event)."

                for edit in pending:
                    CodeEditorTool()._apply_edit_logic(edit)

                PENDING_EDITS_FILE.unlink()
                return f"SUCCESS: All {len(pending)} pending edits have been applied."

        except Exception as e:
            return f"ERROR applying edit: {str(e)}"
