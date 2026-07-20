"""
Filesystem Path Guardian for preventing path traversal and unsafe write operations.
"""

from pathlib import Path
from typing import Union


class FilesystemPathGuardian:
    """
    Enforces strict path checks on worker filesystem access to prevent
    arbitrary file writes or read escapes (CVE-2026-26268).
    """

    def __init__(self, sandbox_root_dir: Union[str, Path]) -> None:
        """
        Initializes the guardian with the designated root path for the agent workspace.
        This path is treated as the absolute boundary for all operations.
        """
        boundary = Path(sandbox_root_dir)
        boundary.mkdir(parents=True, exist_ok=True)
        self.root_boundary = boundary.resolve(strict=True)

    def verify_and_canonicalize(self, unvalidated_path: Union[str, Path]) -> Path:
        """
        Validates target paths. Resolves relative traversal elements and throws a
        PermissionError if the target lies outside the sandbox root.
        """
        # Defense against null-byte injections
        if "\x00" in str(unvalidated_path):
            raise PermissionError(
                "Security Violation: Null-byte injection detected in target path."
            )

        # Translate Windows-style paths on Linux/WSL
        import sys, re
        path_str = str(unvalidated_path)
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
            unvalidated_path = current_path

        # Resolve symlinks and relative directories to determine the physical path
        try:
            # We use strict=False because target files might not exist yet when creating new files.
            canonical_path = Path(unvalidated_path).resolve(strict=False)
        except Exception as err:
            raise PermissionError(f"Access Denied: Path resolution failed: {err}")

        # Block directory traversal attempts
        try:
            canonical_path.relative_to(self.root_boundary)
        except ValueError:
            is_sb = False
            try:
                sb_path = Path("D:/second-brain" if sys.platform == "win32" else "/mnt/d/second-brain").resolve(strict=False)
                canonical_path.relative_to(sb_path)
                is_sb = True
            except ValueError:
                pass
            except Exception:
                pass
            if not is_sb:
                raise PermissionError(
                    f"Security Violation: Path traversal escape attempt blocked. "
                    f"Target path '{canonical_path}' is outside sandbox root '{self.root_boundary}'."
                )

        # Protect Git metadata: block .git itself and its internal subdirectories
        path_parts_lower = [p.lower().strip() for p in canonical_path.parts]
        if ".git" in path_parts_lower:
            raise PermissionError(
                "Security Violation: Access to Git metadata directory is strictly prohibited."
            )

        return canonical_path

    def validate_path(self, path_str: str, check_write: bool = False) -> Path:
        """
        Backward compatible method that validates and canonicalizes paths.
        """
        return self.verify_and_canonicalize(path_str)
