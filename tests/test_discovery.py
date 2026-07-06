# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""Tests for client config discovery loaders."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_checkup.discovery import discover_all
from mcp_checkup.discovery.claude_code import load as load_claude_code
from mcp_checkup.discovery.claude_desktop import load as load_claude_desktop
from mcp_checkup.discovery.cursor import load as load_cursor
from mcp_checkup.discovery.vscode import load as load_vscode
from mcp_checkup.discovery.windsurf import load as load_windsurf
from mcp_checkup.models import Transport


def write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def home(tmp_path: Path) -> Path:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    return fake_home


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    proj = tmp_path / "project"
    proj.mkdir()
    monkeypatch.setattr(Path, "cwd", staticmethod(lambda: proj))
    return proj


@pytest.fixture
def darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "darwin")


STDIO_ENTRY = {"command": "uvx", "args": ["some-server"], "env": {"API_KEY": "sekrit"}}


class TestClaudeDesktop:
    def test_found_macos(self, home: Path, darwin: None) -> None:
        path = write_json(
            home / "Library/Application Support/Claude/claude_desktop_config.json",
            {"mcpServers": {"srv": STDIO_ENTRY}},
        )
        found = load_claude_desktop(home)
        assert len(found) == 1
        d = found[0]
        assert d.client == "claude-desktop"
        assert d.source == str(path)
        assert d.scope == "user"
        assert d.spec.transport is Transport.STDIO
        assert d.spec.command == "uvx"
        # env values stay in the spec; redaction is render's job.
        assert d.spec.env == {"API_KEY": "sekrit"}

    def test_found_windows(self, home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.platform", "win32")
        write_json(
            home / "AppData/Roaming/Claude/claude_desktop_config.json",
            {"mcpServers": {"srv": STDIO_ENTRY}},
        )
        assert len(load_claude_desktop(home)) == 1

    def test_found_linux(self, home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.platform", "linux")
        write_json(
            home / ".config/Claude/claude_desktop_config.json",
            {"mcpServers": {"srv": STDIO_ENTRY}},
        )
        assert len(load_claude_desktop(home)) == 1

    def test_missing_file(self, home: Path, darwin: None) -> None:
        assert load_claude_desktop(home) == []

    def test_malformed_json(self, home: Path, darwin: None) -> None:
        path = home / "Library/Application Support/Claude/claude_desktop_config.json"
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        assert load_claude_desktop(home) == []


class TestClaudeCode:
    def test_three_scopes(self, home: Path, project: Path) -> None:
        write_json(project / ".mcp.json", {"mcpServers": {"proj-srv": STDIO_ENTRY}})
        write_json(
            home / ".claude.json",
            {
                "mcpServers": {"user-srv": {"type": "http", "url": "https://user.example/mcp"}},
                "projects": {
                    str(project): {
                        "mcpServers": {"local-srv": {"type": "sse", "url": "https://local.example"}}
                    },
                    "/some/other/project": {
                        "mcpServers": {"other-srv": {"command": "should-not-appear"}}
                    },
                },
            },
        )
        found = load_claude_code(home)
        by_name = {d.spec.name: d for d in found}
        assert set(by_name) == {"proj-srv", "user-srv", "local-srv"}
        assert by_name["proj-srv"].scope == "project"
        assert by_name["proj-srv"].source == str(project / ".mcp.json")
        assert by_name["user-srv"].scope == "user"
        assert by_name["user-srv"].spec.transport is Transport.HTTP
        assert by_name["local-srv"].scope == "local"
        assert by_name["local-srv"].source == str(home / ".claude.json")
        assert all(d.client == "claude-code" for d in found)

    def test_local_scope_requires_cwd_match(self, home: Path, project: Path) -> None:
        write_json(
            home / ".claude.json",
            {"projects": {"/not/the/cwd": {"mcpServers": {"srv": STDIO_ENTRY}}}},
        )
        assert load_claude_code(home) == []

    def test_missing_files(self, home: Path, project: Path) -> None:
        assert load_claude_code(home) == []

    def test_malformed_json(self, home: Path, project: Path) -> None:
        (project / ".mcp.json").write_text("][", encoding="utf-8")
        (home / ".claude.json").write_text("not json at all", encoding="utf-8")
        assert load_claude_code(home) == []


class TestCursor:
    def test_user_and_project(self, home: Path, project: Path) -> None:
        global_path = write_json(
            home / ".cursor/mcp.json", {"mcpServers": {"global-srv": STDIO_ENTRY}}
        )
        project_path = write_json(
            project / ".cursor/mcp.json",
            {"mcpServers": {"proj-srv": {"url": "https://proj.example/mcp"}}},
        )
        found = load_cursor(home)
        by_name = {d.spec.name: d for d in found}
        assert set(by_name) == {"global-srv", "proj-srv"}
        assert by_name["global-srv"].scope == "user"
        assert by_name["global-srv"].source == str(global_path)
        assert by_name["proj-srv"].scope == "project"
        assert by_name["proj-srv"].source == str(project_path)
        assert all(d.client == "cursor" for d in found)

    def test_missing_files(self, home: Path, project: Path) -> None:
        assert load_cursor(home) == []

    def test_malformed_json(self, home: Path, project: Path) -> None:
        path = home / ".cursor/mcp.json"
        path.parent.mkdir(parents=True)
        path.write_text("{", encoding="utf-8")
        assert load_cursor(home) == []


class TestWindsurf:
    def test_found_with_server_url(self, home: Path) -> None:
        path = write_json(
            home / ".codeium/windsurf/mcp_config.json",
            {"mcpServers": {"remote": {"serverUrl": "https://windsurf.example/mcp"}}},
        )
        found = load_windsurf(home)
        assert len(found) == 1
        d = found[0]
        assert d.client == "windsurf"
        assert d.source == str(path)
        assert d.scope == "user"
        assert d.spec.transport is Transport.HTTP
        assert d.spec.url == "https://windsurf.example/mcp"

    def test_missing_file(self, home: Path) -> None:
        assert load_windsurf(home) == []

    def test_malformed_json(self, home: Path) -> None:
        path = home / ".codeium/windsurf/mcp_config.json"
        path.parent.mkdir(parents=True)
        path.write_text("[1, 2", encoding="utf-8")
        assert load_windsurf(home) == []


class TestVSCode:
    def test_servers_key_and_needs_input(self, home: Path, project: Path, darwin: None) -> None:
        workspace_path = write_json(
            project / ".vscode/mcp.json",
            {
                "servers": {
                    "ws-srv": {
                        "type": "stdio",
                        "command": "npx",
                        "args": ["-y", "some-server", "${input:api-key}"],
                    }
                }
            },
        )
        user_path = write_json(
            home / "Library/Application Support/Code/User/mcp.json",
            {"servers": {"user-srv": {"type": "http", "url": "https://vscode.example/mcp"}}},
        )
        found = load_vscode(home)
        by_name = {d.spec.name: d for d in found}
        assert set(by_name) == {"ws-srv", "user-srv"}
        ws = by_name["ws-srv"]
        assert ws.scope == "project"
        assert ws.source == str(workspace_path)
        assert ws.error == "needs-input"
        user = by_name["user-srv"]
        assert user.scope == "user"
        assert user.source == str(user_path)
        assert user.error is None
        assert all(d.client == "vscode" for d in found)

    def test_mcp_servers_key_ignored(self, home: Path, project: Path, darwin: None) -> None:
        write_json(project / ".vscode/mcp.json", {"mcpServers": {"srv": STDIO_ENTRY}})
        assert load_vscode(home) == []

    def test_missing_files(self, home: Path, project: Path, darwin: None) -> None:
        assert load_vscode(home) == []

    def test_malformed_json(self, home: Path, project: Path, darwin: None) -> None:
        path = project / ".vscode/mcp.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"servers": ', encoding="utf-8")
        assert load_vscode(home) == []


class TestDiscoverAll:
    def test_dedup_identity_across_clients(self, home: Path, project: Path, darwin: None) -> None:
        entry = {"command": "uvx", "args": ["shared-server"]}
        write_json(
            home / "Library/Application Support/Claude/claude_desktop_config.json",
            {"mcpServers": {"shared": entry}},
        )
        write_json(home / ".cursor/mcp.json", {"mcpServers": {"shared": entry}})
        found = discover_all(home=home)
        assert {d.client for d in found} == {"claude-desktop", "cursor"}
        identities = [d.identity() for d in found]
        assert identities[0] == identities[1]
        assert len(set(identities)) == 1

    def test_clients_filter(self, home: Path, project: Path, darwin: None) -> None:
        write_json(
            home / "Library/Application Support/Claude/claude_desktop_config.json",
            {"mcpServers": {"desktop-srv": STDIO_ENTRY}},
        )
        write_json(home / ".cursor/mcp.json", {"mcpServers": {"cursor-srv": STDIO_ENTRY}})
        found = discover_all(home=home, clients=["cursor"])
        assert len(found) == 1
        assert found[0].client == "cursor"
        assert found[0].spec.name == "cursor-srv"

    def test_empty_home(self, home: Path, project: Path, darwin: None) -> None:
        assert discover_all(home=home) == []
