"""Antigravity MCP registrar.

Antigravity stores MCP server configuration in ``~/.gemini/config/mcp_config.json``
under the top-level ``mcpServers`` key. This registrar edits that JSON file directly.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .base import MCPRegistrar, RegisterResult, RegisterStatus, ServerSpec

logger = logging.getLogger(__name__)


def _antigravity_home_dir() -> Path:
    """Return the Antigravity/Gemini home/config directory."""
    env_path = os.environ.get("GEMINI_CONFIG_DIR", os.environ.get("ANTIGRAVITY_CONFIG_DIR", "")).strip()
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / ".gemini" / "config"


def _antigravity_config_path() -> Path:
    """Return the active Antigravity config path."""
    return _antigravity_home_dir() / "mcp_config.json"


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON file, returning empty dict if absent or unparseable."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _entry_to_spec(name: str, entry: dict[str, Any]) -> ServerSpec:
    command = str(entry.get("command", ""))
    args_value = entry.get("args", [])
    if isinstance(args_value, list):
        args = tuple(str(x) for x in args_value)
    else:
        args = ()
    env_value = entry.get("env", {})
    env: dict[str, str] = {}
    if isinstance(env_value, dict):
        env = {str(k): str(v) for k, v in env_value.items()}
    return ServerSpec(name=name, command=command, args=args, env=env)


def _spec_to_entry(spec: ServerSpec) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "command": spec.command,
    }
    if spec.args:
        entry["args"] = list(spec.args)
    if spec.env:
        entry["env"] = dict(spec.env)
    return entry


def _specs_equivalent(a: ServerSpec, b: ServerSpec) -> bool:
    return (
        a.name == b.name
        and a.command == b.command
        and tuple(a.args) == tuple(b.args)
        and dict(a.env) == dict(b.env)
    )


def _diff_specs(existing: ServerSpec, requested: ServerSpec) -> str:
    parts: list[str] = []
    if existing.command != requested.command:
        parts.append(f"command {existing.command!r} -> {requested.command!r}")
    if tuple(existing.args) != tuple(requested.args):
        parts.append(f"args {list(existing.args)} -> {list(requested.args)}")
    if dict(existing.env) != dict(requested.env):
        parts.append(f"env {dict(existing.env)} -> {dict(requested.env)}")
    if not parts:
        return "spec differs in unidentified field(s)"
    return "; ".join(parts)


class AntigravityRegistrar(MCPRegistrar):
    """Register MCP servers with Antigravity."""

    name = "antigravity"
    display_name = "Antigravity"

    def __init__(self, *, config_path: Path | None = None) -> None:
        self._config_path = config_path or _antigravity_config_path()

    def detect(self) -> bool:
        return self._config_path.parent.is_dir()

    def get_server(self, server_name: str) -> ServerSpec | None:
        data = _read_json(self._config_path)
        mcp = data.get("mcpServers", {})
        if not isinstance(mcp, dict):
            return None
        entry = mcp.get(server_name)
        if not isinstance(entry, dict):
            return None
        return _entry_to_spec(server_name, entry)

    def register_server(self, spec: ServerSpec, *, force: bool = False) -> RegisterResult:
        existing = self.get_server(spec.name)

        if existing is not None and _specs_equivalent(existing, spec):
            return RegisterResult(RegisterStatus.ALREADY, "matches current configuration")

        if existing is not None and not force:
            return RegisterResult(
                RegisterStatus.MISMATCH,
                _diff_specs(existing, spec),
            )

        if existing is not None and force:
            # Remove the existing entry before rewriting.
            self.unregister_server(spec.name)

        return self._write_entry(spec)

    def unregister_server(self, server_name: str) -> bool:
        data = _read_json(self._config_path)
        mcp = data.get("mcpServers", {})
        if not isinstance(mcp, dict) or server_name not in mcp:
            return False
        del mcp[server_name]
        data["mcpServers"] = mcp
        try:
            _write_json(self._config_path, data)
        except OSError:
            return False
        return True

    def _write_entry(self, spec: ServerSpec) -> RegisterResult:
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            data = _read_json(self._config_path)
            mcp = data.setdefault("mcpServers", {})
            mcp[spec.name] = _spec_to_entry(spec)
            _write_json(self._config_path, data)
        except OSError as exc:
            return RegisterResult(RegisterStatus.FAILED, f"could not write {self._config_path}: {exc}")
        return RegisterResult(RegisterStatus.REGISTERED, f"wrote to {self._config_path}")
