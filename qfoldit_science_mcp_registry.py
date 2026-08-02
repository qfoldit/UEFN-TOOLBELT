"""
qFoldIT Science MCP Registry
=============================
Separate from the IP/brand Trust Runtime — this regulates which SCIENTIFIC
MCP servers the backend is allowed to connect at runtime, and under what
conditions. Same philosophy: default caution, everything sourced, nothing
silently escalated.

Why a separate registry instead of reusing license_manifest.json:
the trust runtime above answers "is this brand asset legally usable?".
This answers a different question: "is this MCP server safe/stable enough
to auto-connect, or does it need an explicit opt-in?" — a stability/trust
question, not a copyright question.

STATUS LEVELS
-------------
  verified    - you've run it, it works, output has been checked against
                a known-good reference (e.g. the VQE H2 benchmark in
                qfoldit-quantum, or Boltz's own account/estimate endpoints).
                Auto-connects.
  connected   - actively linked to this account/session right now
                (e.g. an already-authorized third-party API). Auto-connects,
                but every call it makes should still be logged.
  best_effort - community bridge, functionally reachable, but not
                independently verified end-to-end. Requires explicit
                `allow_best_effort=True` to connect.
  reference_only - documentation/instructions for connecting an external
                engine (e.g. Unreal/Unity/Omniverse bridges); nothing here
                actually runs in this environment. Never auto-connects.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field


@dataclass
class MCPServerRecord:
    name: str
    provider: str
    license: str
    status: str                    # verified | connected | best_effort | reference_only
    capabilities: list[str] = field(default_factory=list)
    source: str = ""                # repo URL or doc reference
    requires_credentials: bool = False
    notes: str = ""


class ScienceMCPRegistry:
    def __init__(
        self,
        registry_path: str = "science_mcp_registry.json",
        connection_log_path: str = "science_mcp_connections.log.jsonl",
    ):
        self.registry_path = registry_path
        self.connection_log_path = connection_log_path
        self.servers: dict[str, MCPServerRecord] = self._load()

    def _load(self) -> dict[str, MCPServerRecord]:
        if not os.path.exists(self.registry_path):
            return {}
        with open(self.registry_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        out = {}
        for key, rec in raw.items():
            if key.startswith("_"):
                continue
            out[key] = MCPServerRecord(**rec)
        return out

    def list_available(self, status_filter: str | None = None) -> list[str]:
        if status_filter is None:
            return list(self.servers.keys())
        return [k for k, v in self.servers.items() if v.status == status_filter]

    def can_connect(self, name: str, allow_best_effort: bool = False) -> tuple[bool, str]:
        rec = self.servers.get(name)
        if rec is None:
            return False, f"'{name}' is not in science_mcp_registry.json — unregistered servers don't auto-connect."
        if rec.status in ("verified", "connected"):
            return True, f"OK — {rec.status}"
        if rec.status == "best_effort":
            if allow_best_effort:
                return True, "OK — best_effort, explicitly allowed"
            return False, f"'{name}' is best_effort (community bridge, not independently verified). Pass allow_best_effort=True to connect anyway."
        if rec.status == "reference_only":
            return False, f"'{name}' is reference/instructions only — there is nothing here to connect to in this environment."
        return False, f"Unknown status '{rec.status}' for '{name}' — treat as blocked until classified."

    def connect(self, name: str, allow_best_effort: bool = False) -> MCPServerRecord | None:
        ok, reason = self.can_connect(name, allow_best_effort=allow_best_effort)
        self._log_connection(name, ok, reason)
        if not ok:
            return None
        return self.servers[name]

    def _log_connection(self, name: str, ok: bool, reason: str) -> None:
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "server": name,
            "connected": ok,
            "reason": reason,
        }
        with open(self.connection_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def describe(self, name: str) -> str:
        rec = self.servers.get(name)
        if rec is None:
            return f"'{name}' not registered."
        lines = [
            f"{rec.name} ({rec.provider}) — status: {rec.status}, license: {rec.license}",
            f"Capabilities: {', '.join(rec.capabilities) if rec.capabilities else 'n/a'}",
            f"Source: {rec.source}",
            f"Requires credentials: {rec.requires_credentials}",
        ]
        if rec.notes:
            lines.append(f"Notes: {rec.notes}")
        return "\n".join(lines)
