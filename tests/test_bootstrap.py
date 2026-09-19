import subprocess
from types import SimpleNamespace

from fireflyer import bootstrap


def _args(**overrides):
    defaults = dict(
        target="user@host",
        base="/srv/blog",
        port="22",
        identity=None,
        print_only=False,
    )
    return SimpleNamespace(**{**defaults, **overrides})


def test_remote_script_targets_the_base_directory():
    script = bootstrap.remote_script("/srv/blog")
    assert 'BASE=/srv/blog' in script
    assert "mkdir -p \"$BASE/releases\"" in script


def test_remote_script_installs_the_release_script_verbatim():
    """The body is sent as-is, so it must survive the heredoc unchanged."""
    script = bootstrap.remote_script("/srv/blog")
    installed = script.split("cat > \"$BASE/release.sh\" <<'__FIREFLYER_RELEASE_SCRIPT__'\n")[1]
    assert installed.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in installed


def test_remote_script_is_posix_line_endings_only():
    """Guards the failure that made the first real run die on `set -euo pipefail`."""
    assert "\r" not in bootstrap.remote_script("/srv/blog")


def test_run_sends_bytes_so_windows_does_not_rewrite_newlines(monkeypatch):
    """The actual bug: text-mode stdin turned every \\n into \\r\\n on Windows.

    bash then read `set -euo pipefail\\r` and rejected the option name. Asserting
    the payload is bytes, and CR-free, is what stops it coming back.
    """
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
    assert bootstrap.run(_args()) == 0

    assert isinstance(captured["input"], bytes)
    assert b"\r" not in captured["input"]
    assert b"set -euo pipefail" in captured["input"]


def test_identity_is_passed_to_ssh(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
    bootstrap.run(_args(identity="/keys/deploy"))

    command = captured["command"]
    assert command[0] == "ssh"
    assert "-i" in command
    assert command[command.index("-i") + 1] == "/keys/deploy"


def test_rejects_a_base_that_is_not_absolute(capsys):
    assert bootstrap.run(_args(base="relative/dir")) == 2
    assert "absolute POSIX path" in capsys.readouterr().err


def test_names_the_msys_cause_when_a_windows_path_arrives(capsys):
    """Git Bash rewrites POSIX-looking arguments before Python ever sees them."""
    assert bootstrap.run(_args(base="D:/srv/blog")) == 2
    assert "MSYS_NO_PATHCONV=1" in capsys.readouterr().err
