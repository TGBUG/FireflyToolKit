"""Onboard a blog repository, from an empty GitHub repository to a working one.

Creating the repository stays manual, because that needs `Administration: write`
on every repository the operator owns, and holding that permanently is a larger
exposure than one step is worth. See ADR-0003.

Everything after that is automated, and needs only `Contents: write` plus
`Actions: write`:

1. mirror Firefly's history in, pushing `master` first so it becomes the default
   branch (the first ref pushed into an empty repository wins, and pushing
   everything at once lets GitHub pick a branch of its own choosing)
2. clone a working tree and point `upstream` at Firefly
3. inject the layer, commit, and push
4. disable the theme's own `build.yml` and `deploy.yml`, which trigger on every
   push to master and cost far more runner time than the deploy does

Step 4 has to follow the push: GitHub registers a repository's workflows when
work first arrives on a branch, so immediately after mirroring there are none to
disable, and a check at that moment reports an empty list rather than an error.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

from fireflyer import github, gitutil, inject

UPSTREAM_WORKFLOWS = ("build.yml", "deploy.yml")
REGISTRATION_ATTEMPTS = 10
REGISTRATION_DELAY = 3.0

MANUAL_STEPS = """\
what is left, and it is manual on purpose
  - create a non-root deploy user on the server, and install its public key.
    It needs write access to the directory you pass to bootstrap-vps, nothing else
  - in the hosting panel: create the site for your domain with its document root
    set to <base>/current, and issue TLS from the panel
  - add the VPS_HOST, VPS_USER, VPS_SSH_KEY and VPS_BASE repository secrets

    the push above already started a deploy run, and it will have failed: the
    secrets did not exist yet. Once they do, re-run it from the Actions tab
    (the workflow has a manual trigger for exactly this reason)
  - delete Firefly's demo content from src/content/posts/ and src/content/dynamic/
  - set siteConfig.site_url in src/config/siteConfig.ts
"""


def ensure_upstream(repo: Path, url: str) -> str:
    """Point the `upstream` remote at Firefly, adding or correcting it."""
    current = gitutil.try_git(repo, "remote", "get-url", "upstream")
    if current is None:
        gitutil.run_git(repo, "remote", "add", "upstream", url)
        return f"upstream: added -> {url}"
    if current.strip() != url:
        gitutil.run_git(repo, "remote", "set-url", "upstream", url)
        return f"upstream: was {current.strip()}, now {url}"
    return f"upstream: already {url}"


def _commit_identity(repo: Path) -> list[str]:
    """Let git fall back to a neutral identity if the operator has none set."""
    if gitutil.try_git(repo, "config", "user.email"):
        return []
    return ["-c", "user.name=fireflyer", "-c", "user.email=fireflyer@localhost"]


def mirror(slug: str, upstream: str, auth: str, work: Path) -> None:
    url = f"https://github.com/{slug}.git"
    scratch = Path(tempfile.mkdtemp(prefix="fireflyer-"))
    bare = scratch / "upstream"
    try:
        print("  mirroring Firefly (this transfers about 130 MB)...", flush=True)
        gitutil.run_git_in(scratch, "clone", "--bare", upstream, str(bare))

        print("  pushing master on its own, so it becomes the default branch...", flush=True)
        gitutil.run_git(bare, "push", url, "master:master", auth=auth)

        print("  pushing the remaining branches and tags...", flush=True)
        gitutil.run_git(bare, "push", "--mirror", url, auth=auth)

        print(f"  cloning a working tree into {work}...", flush=True)
        gitutil.run_git_in(scratch, "clone", str(bare), str(work))
        gitutil.run_git(work, "remote", "set-url", "origin", url)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def wait_for_registration(slug: str, auth: str) -> dict[str, str]:
    """Poll briefly: GitHub registers workflows shortly after the first push."""
    states: dict[str, str] = {}
    for attempt in range(REGISTRATION_ATTEMPTS):
        states = github.workflow_states(slug, auth)
        if states:
            return states
        if attempt == 0:
            print("  waiting for GitHub to register the workflows...", flush=True)
        time.sleep(REGISTRATION_DELAY)
    return states


def disable_upstream_ci(slug: str, auth: str) -> list[str]:
    states = wait_for_registration(slug, auth)
    if not states:
        raise RuntimeError(
            "GitHub still reports no workflows for this repository, so the theme's "
            "build.yml and deploy.yml could not be disabled. Re-run init once they "
            "appear in the repository's Actions tab"
        )

    messages: list[str] = []
    for name in UPSTREAM_WORKFLOWS:
        state = states.get(name)
        if state is None:
            messages.append(f"{name}: not registered, nothing to do")
        elif state == "disabled_manually":
            messages.append(f"{name}: already disabled")
        else:
            github.disable_workflow(slug, name, auth)
            messages.append(f"{name}: disabled (was {state})")
    return messages


def cancel_upstream_runs(slug: str, auth: str) -> list[str]:
    """Stop the theme's CI runs that this onboarding push started.

    Disabling a workflow does not stop runs already queued by the push that
    registered it, and those runs are precisely the minutes this is all about:
    `build.yml` and `deploy.yml` together are several times the cost of our own
    deploy. They can still be cancelled, so they are.
    """
    payload = github.request("GET", f"/repos/{slug}/actions/runs?per_page=100", auth) or {}
    live = {"in_progress", "queued", "pending", "requested", "waiting"}
    cancelled: list[str] = []
    for run in payload.get("workflow_runs", []):  # type: ignore[union-attr]
        name = str(run.get("path", "")).rsplit("/", 1)[-1]
        if name not in UPSTREAM_WORKFLOWS or run.get("status") not in live:
            continue
        try:
            github.request("POST", f"/repos/{slug}/actions/runs/{run['id']}/cancel", auth)
            cancelled.append(f"{name} run #{run.get('run_number')}")
        except github.GitHubError:
            pass  # it finished on its own in the meantime
    return cancelled


def default_branch_warning(slug: str, auth: str) -> str | None:
    branch = github.default_branch(slug, auth)
    if branch is None or branch == "master":
        return None
    return (
        f"the default branch is '{branch}', not 'master'. Set it under Settings -> General. "
        "This should not happen when init does the mirroring; it means the repository was "
        "seeded another way."
    )


def run(args) -> int:
    slug = args.repo
    if slug.count("/") != 1:
        print(f"expected owner/name, got {slug!r}", file=sys.stderr)
        return 2

    auth = github.token()
    if auth is None:
        print(
            "init needs a GitHub token in GH_TOKEN or GITHUB_TOKEN, with Contents: write "
            "and Actions: write for this repository.",
            file=sys.stderr,
        )
        return 2

    work = Path(args.dir or slug.split("/", 1)[-1]).resolve()
    if work.exists():
        print(f"{work} already exists; move it aside or pass --dir", file=sys.stderr)
        return 2

    print(f"fireflyer init -> {slug} into {work}\n", flush=True)

    try:
        branches = github.request("GET", f"/repos/{slug}/branches", auth)
    except github.GitHubError as error:
        print(f"cannot reach {slug}: {error}", file=sys.stderr)
        return 2
    if branches:
        names = ", ".join(branch["name"] for branch in branches[:5])  # type: ignore[index]
        print(
            f"{slug} is not empty -- it already has {len(branches)} branch(es): {names}. "
            "Create a new, empty repository instead.",
            file=sys.stderr,
        )
        return 2

    mirror(slug, args.upstream, auth, work)
    print(f"  {ensure_upstream(work, args.upstream)}")

    warning = default_branch_warning(slug, auth)
    if warning:
        print(f"  default branch: WARNING -- {warning}", file=sys.stderr)

    if not inject.inject_repository(work, announce=False):
        print("  injected the layer")

    print("\n  committing and pushing, so the workflows register...", flush=True)
    gitutil.run_git(work, "add", "-A")
    gitutil.run_git(
        work, *_commit_identity(work), "commit", "-q", "-m", "chore: add Fireflyer"
    )
    gitutil.run_git(work, "push", "-q", "origin", "master", auth=auth)

    if args.no_disable_upstream_ci:
        print("  upstream CI: skipped (--no-disable-upstream-ci)")
    else:
        try:
            for message in disable_upstream_ci(slug, auth):
                print(f"  upstream CI {message}")
            for message in cancel_upstream_runs(slug, auth):
                print(f"  upstream CI {message}: cancelled")
        except (github.GitHubError, RuntimeError) as error:
            print(f"  upstream CI: WARNING -- {error}", file=sys.stderr)

    print()
    print(MANUAL_STEPS)
    return 0
