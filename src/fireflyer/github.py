"""A very small GitHub REST client.

Only the handful of calls Fireflyer needs: reading a repository's workflow state,
and disabling a workflow. Written against the standard library so the tool has no
runtime dependency beyond PyYAML.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API_ROOT = "https://api.github.com"
TOKEN_ENV_VARS = ("GH_TOKEN", "GITHUB_TOKEN")


class GitHubError(RuntimeError):
    """A GitHub API call failed."""


def token() -> str | None:
    """The first configured token, if any."""
    for name in TOKEN_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return value
    return None


def request(method: str, path: str, auth: str, body: dict | None = None) -> object | None:
    """Call the GitHub API, returning the decoded body (None for 204s)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {auth}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "fireflyer",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"

    call = urllib.request.Request(
        f"{API_ROOT}{path}", data=data, headers=headers, method=method.upper()
    )
    try:
        with urllib.request.urlopen(call, timeout=25) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace").strip()
        raise GitHubError(f"{method} {path} -> HTTP {error.code}: {detail}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise GitHubError(f"{method} {path} -> {error}") from error

    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError as error:
        raise GitHubError(f"{method} {path} -> unreadable response") from error


def default_branch(slug: str, auth: str) -> str | None:
    """The repository's default branch, which is not necessarily master."""
    payload = request("GET", f"/repos/{slug}", auth) or {}
    branch = payload.get("default_branch")  # type: ignore[union-attr]
    return branch if isinstance(branch, str) else None


def workflow_states(slug: str, auth: str) -> dict[str, str]:
    """Map workflow filename -> state.

    Empty means GitHub has registered no workflows at all, which is not the same
    as "the workflows are gone": Actions may be switched off for the repository,
    in which case every workflow is invisible here and none of them can be
    disabled through this API. Callers must not read an empty result as success.
    """
    payload = request("GET", f"/repos/{slug}/actions/workflows", auth) or {}
    return {
        entry["path"].rsplit("/", 1)[-1]: entry["state"]
        for entry in payload.get("workflows", [])  # type: ignore[union-attr]
    }


def disable_workflow(slug: str, filename: str, auth: str) -> None:
    """Disable one workflow by filename (the API accepts the name as its id)."""
    request("PUT", f"/repos/{slug}/actions/workflows/{filename}/disable", auth)
