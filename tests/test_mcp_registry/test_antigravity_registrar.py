"""Tests for the Antigravity MCP registrar."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from headroom.mcp_registry.base import RegisterStatus, ServerSpec
from headroom.mcp_registry.antigravity import AntigravityRegistrar


def _make_registrar(tmp_path: Path) -> AntigravityRegistrar:
    return AntigravityRegistrar(config_path=tmp_path / "mcp_config.json")


def _spec() -> ServerSpec:
    return ServerSpec(
        name="headroom",
        command="headroom",
        args=("mcp", "serve"),
        env={},
    )


# ----------------------------------------------------------------------
# detect()
# ----------------------------------------------------------------------


def test_detect_true_when_config_dir_exists(tmp_path: Path) -> None:
    # config_path is tmp_path / "mcp_config.json", parent is tmp_path
    reg = _make_registrar(tmp_path)
    assert reg.detect() is True


def test_detect_false_when_config_dir_missing() -> None:
    reg = AntigravityRegistrar(config_path=Path("/nonexistent/mcp_config.json"))
    assert reg.detect() is False


# ----------------------------------------------------------------------
# get_server()
# ----------------------------------------------------------------------


def test_get_server_returns_none_when_unregistered(tmp_path: Path) -> None:
    reg = _make_registrar(tmp_path)
    assert reg.get_server("headroom") is None


def test_get_server_reads_config(tmp_path: Path) -> None:
    cfg = tmp_path / "mcp_config.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "headroom": {
                        "command": "headroom",
                        "args": ["mcp", "serve"],
                        "env": {"HEADROOM_PROXY_URL": "http://127.0.0.1:9000"},
                    }
                }
            }
        )
    )
    reg = _make_registrar(tmp_path)
    got = reg.get_server("headroom")
    assert got is not None
    assert got.command == "headroom"
    assert got.args == ("mcp", "serve")
    assert got.env == {"HEADROOM_PROXY_URL": "http://127.0.0.1:9000"}


# ----------------------------------------------------------------------
# register_server()
# ----------------------------------------------------------------------


def test_register_writes_new_file(tmp_path: Path) -> None:
    reg = _make_registrar(tmp_path)
    spec = _spec()
    res = reg.register_server(spec)
    assert res.status == RegisterStatus.REGISTERED

    cfg = tmp_path / "mcp_config.json"
    assert cfg.exists()
    data = json.loads(cfg.read_text())
    assert data["mcpServers"]["headroom"]["command"] == "headroom"


def test_register_already_matches(tmp_path: Path) -> None:
    reg = _make_registrar(tmp_path)
    spec = _spec()
    reg.register_server(spec)
    res = reg.register_server(spec)
    assert res.status == RegisterStatus.ALREADY


def test_register_mismatch_without_force(tmp_path: Path) -> None:
    reg = _make_registrar(tmp_path)
    spec = _spec()
    reg.register_server(spec)

    new_spec = ServerSpec("headroom", "other_cmd", (), {})
    res = reg.register_server(new_spec)
    assert res.status == RegisterStatus.MISMATCH


def test_register_mismatch_with_force(tmp_path: Path) -> None:
    reg = _make_registrar(tmp_path)
    spec = _spec()
    reg.register_server(spec)

    new_spec = ServerSpec("headroom", "other_cmd", (), {})
    res = reg.register_server(new_spec, force=True)
    assert res.status == RegisterStatus.REGISTERED

    got = reg.get_server("headroom")
    assert got is not None
    assert got.command == "other_cmd"


# ----------------------------------------------------------------------
# unregister_server()
# ----------------------------------------------------------------------


def test_unregister_returns_false_when_missing(tmp_path: Path) -> None:
    reg = _make_registrar(tmp_path)
    assert reg.unregister_server("headroom") is False


def test_unregister_removes_entry(tmp_path: Path) -> None:
    reg = _make_registrar(tmp_path)
    spec = _spec()
    reg.register_server(spec)
    assert reg.unregister_server("headroom") is True
    assert reg.get_server("headroom") is None
