"""
Actuation Lease — signed capability token for worker execution.

Each lease binds: task_id, agent_id, allowed_tools, writable_paths,
network policy, TTL, and an HMAC signature.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class ActuationLease:
    task_id: str
    agent_id: str
    allowed_tools: list[str]
    writable_paths: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    network_allowed: bool = False
    issued_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    signature: str = ""

    _secret_key: Optional[bytes] = None

    @classmethod
    def _get_secret_key(cls) -> bytes:
        if cls._secret_key is not None:
            return cls._secret_key
        try:
            key_path = Path.home() / ".kinthic" / "config" / "hmac_key.bin"
            try:
                key_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            if key_path.exists():
                cls._secret_key = key_path.read_bytes()
            else:
                cls._secret_key = os.urandom(32)
                key_path.write_bytes(cls._secret_key)
                try:
                    key_path.chmod(0o600)
                except OSError:
                    pass
        except Exception:
            # Fallback to ephemeral in-memory key if filesystem access is restricted
            if cls._secret_key is None:
                cls._secret_key = os.urandom(32)
        return cls._secret_key

    def _canonical_payload(self) -> str:
        data = {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "allowed_tools": sorted(self.allowed_tools),
            "writable_paths": sorted(self.writable_paths),
            "allowed_domains": sorted(self.allowed_domains),
            "network_allowed": self.network_allowed,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    def sign(self) -> "ActuationLease":
        key = self._get_secret_key()
        payload = self._canonical_payload()
        sig = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        self.signature = sig
        return self

    @classmethod
    def issue(
        cls,
        task_id: str,
        agent_id: str,
        ttl_seconds: float = 600.0,
        allowed_tools: Optional[list[str]] = None,
        writable_paths: Optional[list[str]] = None,
        allowed_domains: Optional[list[str]] = None,
        network_allowed: bool = False,
    ) -> "ActuationLease":
        now = time.time()
        lease = cls(
            task_id=task_id,
            agent_id=agent_id,
            allowed_tools=allowed_tools or ["run_terminal_command"],
            writable_paths=writable_paths or [],
            allowed_domains=allowed_domains or [],
            network_allowed=network_allowed,
            issued_at=now,
            expires_at=now + ttl_seconds,
        )
        return lease.sign()

    def verify_signature(self) -> bool:
        if not self.signature:
            return False
        key = self._get_secret_key()
        expected = hmac.new(
            key, self._canonical_payload().encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, self.signature)

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def validate(self, tool_name: str) -> bool:
        """Validate lease for a single tool invocation."""
        if self.is_expired():
            return False
        if not self.verify_signature():
            return False
        return tool_name in self.allowed_tools

    def validate_spawn(self, tools: list[str]) -> bool:
        """Validate lease before spawning a worker with the given tool set."""
        if self.is_expired():
            return False
        if not self.verify_signature():
            return False
        if not tools:
            return False
        allowed = set(self.allowed_tools)
        return all(t in allowed for t in tools)

    def validate_writable_path(
        self, path: str, workspace_root: Path | None = None
    ) -> bool:
        """Return True if path is within lease writable scope."""
        normalized = str(Path(path).resolve().as_posix())
        if self.writable_paths:
            for allowed in self.writable_paths:
                prefix = str(Path(allowed).resolve().as_posix()).rstrip("/")
                if normalized == prefix or normalized.startswith(prefix + "/"):
                    return True
            return False
        if workspace_root is not None:
            ws = str(workspace_root.resolve().as_posix()).rstrip("/")
            return normalized == ws or normalized.startswith(ws + "/")
        return False

    def write_egress_policy(self, workspace_dir: Path) -> None:
        """Write per-worker egress policy for the network proxy."""
        worker_id = workspace_dir.name
        policy_root = Path.home() / ".kinthic" / "workers" / worker_id
        try:
            policy_root.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        policy_file = policy_root / ".egress_policy.json"
        policy = {
            "network_allowed": self.network_allowed,
            "allowed_domains": self.allowed_domains,
        }
        policy_file.write_text(json.dumps(policy), encoding="utf-8")

    def to_token(self) -> str:
        """Serialize lease to a signed token string."""
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_token(cls, token: str) -> Optional["ActuationLease"]:
        try:
            data = json.loads(token)
            lease = cls(
                **{k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            )
            if not lease.verify_signature() or lease.is_expired():
                return None
            return lease
        except (json.JSONDecodeError, TypeError):
            return None
