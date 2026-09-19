"""Thin wrappers around the git commands Fireflyer needs."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

MERGE_DRIVER = "ours"

# Lets git authenticate with the same fine-grained token the API calls use, so
# onboarding does not also require the operator's git credential manager to be
# set up for a repository it has never seen. The token is read from the
# environment by the helper rather than passed on the command line.
TOKEN_HELPER = "!f() { echo username=x-access-token; echo password=$GH_TOKEN; }; f"

_SSH_REMOTE = re.compile(r"^(?:ssh://)?[^@/]+@[^:/]+[:/](?P<slug>[^/]+/[^/]+?)(?:\.git)?/?$")
_URL_REMOTE = re.compile(r"^(?:https?|git)://[^/]+/(?P<slug>[^/]+/[^/]+?)(?:\.git)?/?$")


class GitError(RuntimeError):
    """A git command failed."""


def _command(*args: str, auth: str | None = None) -> list[str]:
    command = ["git"]
    if auth:
        command += ["-c", f"credential.helper={TOKEN_HELPER}"]
    return command + list(args)


def _dispatch(command: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise GitError(f"{' '.join(command[1:])} failed: {detail}")
    return result.stdout


def run_git(repo: Path, *args: str, auth: str | None = None) -> str:
    """Run git inside *repo* and return its stdout, raising on failure."""
    return _dispatch(_command("-C", str(repo), *args, auth=auth))


def run_git_in(cwd: Path, *args: str, auth: str | None = None) -> str:
    """Run git with an arbitrary working directory, for commands like clone."""
    return _dispatch(_command(*args, auth=auth), cwd=cwd)


def try_git(repo: Path, *args: str) -> str | None:
    """Run git inside *repo*, returning None instead of raising on failure."""
    try:
        return run_git(repo, *args)
    except GitError:
        return None


def is_repo(path: Path) -> bool:
    """Whether *path* is inside a git work tree."""
    if not path.is_dir():
        return False
    return try_git(path, "rev-parse", "--git-dir") is not None


def remote_slug(repo: Path, remote: str = "origin") -> str | None:
    """Return ``owner/name`` for *remote*, or None if it has no usable URL."""
    url = try_git(repo, "remote", "get-url", remote)
    if url is None:
        return None
    url = url.strip()
    for pattern in (_SSH_REMOTE, _URL_REMOTE):
        match = pattern.match(url)
        if match:
            return match.group("slug")
    return None


def ignored_paths(repo: Path, paths: list[Path]) -> list[Path]:
    """Return the subset of *paths* (repo-relative) that git would ignore."""
    if not paths:
        return []
    # Bytes, for the same reason bootstrap.py sends bytes: a text-mode stdin on
    # Windows turns each \n into \r\n, and git would then be asked about paths
    # that end in a carriage return, match none of them, and report nothing.
    payload = "\n".join(str(path).replace("\\", "/") for path in paths).encode("utf-8")
    result = subprocess.run(
        ["git", "-C", str(repo), "check-ignore", "--stdin"],
        input=payload,
        capture_output=True,
    )
    output = result.stdout.decode("utf-8", "replace")
    return [Path(line.strip()) for line in output.splitlines() if line.strip()]


def has_merge_driver(repo: Path) -> bool:
    """Whether the ``merge.ours`` driver is configured in this clone.

    The driver lives in ``.git/config``, which is never committed, so a fresh
    clone always starts without it.
    """
    return try_git(repo, "config", "--get", f"merge.{MERGE_DRIVER}.driver") is not None


def configure_merge_driver(repo: Path) -> None:
    """Define the driver that ``merge=ours`` in ``.gitattributes`` refers to."""
    run_git(repo, "config", f"merge.{MERGE_DRIVER}.name", MERGE_DRIVER)
    run_git(repo, "config", f"merge.{MERGE_DRIVER}.driver", "true")
