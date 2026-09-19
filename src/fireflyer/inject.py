"""Write the injected layer into a blog repository.

The layer is a directory tree that mirrors the blog repository root, so the
mapping is almost always by identity. It is idempotent: running it twice reports
every file as ``unchanged``, and it overwrites on ``update`` because Fireflyer
is the single source of truth for everything it injects.
"""

from __future__ import annotations

import difflib
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from fireflyer import gitutil

REPO_PLACEHOLDER = "__FIREFLYER_REPO__"

# Files git or other tooling interprets specially are stored without their
# leading dot and renamed here. A `.gitattributes` inside Fireflyer's own tree
# would apply its attributes to that subtree, and Python build backends handle
# leading-dot files inside a package badly.
RENAMES = {
    "gitattributes": ".gitattributes",
    "node-version": ".node-version",
}

# Only these suffixes are searched for placeholders. Everything else is copied
# byte for byte, so the multi-megabyte CMS bundle is never decoded.
TEMPLATED_SUFFIXES = {".yml", ".yaml", ".md", ".sh", ".html"}

_DIFF_CONTEXT = 2
_DIFF_MAX_LINES = 40


class Action(Enum):
    CREATE = "create"
    UPDATE = "update"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class Change:
    action: Action
    path: Path
    payload: bytes
    existing: bytes | None


def layer_root() -> Traversable:
    root = files("fireflyer") / "layer"
    if not root.is_dir():
        raise RuntimeError(
            "the injectable layer is missing from the installed package; "
            "reinstall fireflyer or run from a checkout"
        )
    return root


def iter_layer(node: Traversable | None = None, prefix: Path | None = None):
    """Yield ``(layer-relative path, node)`` for every file in the layer."""
    node = node if node is not None else layer_root()
    prefix = prefix if prefix is not None else Path()
    for child in sorted(node.iterdir(), key=lambda entry: entry.name):
        relative = prefix / child.name
        if child.is_dir():
            yield from iter_layer(child, relative)
        else:
            yield relative, child


def destination(relative: Path) -> Path:
    """Map a layer-relative path to its destination inside a blog repository."""
    return Path(*(RENAMES.get(part, part) for part in relative.parts))


def render(relative: Path, data: bytes, context: dict[str, str]) -> bytes:
    """Substitute placeholders in text files; return everything else untouched."""
    if relative.suffix.lower() not in TEMPLATED_SUFFIXES:
        return data
    text = data.decode("utf-8")
    for key, value in context.items():
        text = text.replace(key, value)
    return text.encode("utf-8")


def build_context(repo: Path) -> dict[str, str]:
    """Values substituted into the layer at inject time."""
    slug = gitutil.remote_slug(repo)
    if slug is None:
        raise RuntimeError(
            f"{repo} has no usable 'origin' remote. Fireflyer needs it to know "
            "which repository the CMS should read and write; add one with "
            "'git remote add origin <url>'."
        )
    return {REPO_PLACEHOLDER: slug}


def plan(repo: Path, context: dict[str, str]) -> list[Change]:
    changes: list[Change] = []
    for relative, node in iter_layer():
        payload = render(relative, node.read_bytes(), context)
        target = repo / destination(relative)
        existing = target.read_bytes() if target.is_file() else None
        if existing is None:
            action = Action.CREATE
        elif existing == payload:
            action = Action.UNCHANGED
        else:
            action = Action.UPDATE
        changes.append(Change(action, destination(relative), payload, existing))
    return changes


def _describe_diff(change: Change) -> str:
    if change.existing is None:
        return ""
    try:
        before = change.existing.decode("utf-8").splitlines(keepends=True)
        after = change.payload.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return "      (binary file differs)\n"
    diff = list(
        difflib.unified_diff(before, after, "current", "fireflyer", n=_DIFF_CONTEXT)
    )
    if not diff:
        return ""
    body = diff[:_DIFF_MAX_LINES]
    text = "".join(f"      {line}" for line in body)
    if len(diff) > len(body):
        text += f"      … {len(diff) - len(body)} more diff lines\n"
    return text


def report(changes: list[Change]) -> None:
    for change in changes:
        print(f"  {change.action.value:<9} {change.path.as_posix()}")
        if change.action is Action.UPDATE:
            printed = _describe_diff(change)
            if printed:
                print(printed, end="")
    counts = Counter(change.action.value for change in changes)
    summary = ", ".join(f"{counts[name]} {name}" for name in ("create", "update", "unchanged") if counts[name])
    print(f"\n{summary}")


def _warn_ignored(repo: Path, changes: list[Change]) -> None:
    candidates = [change.path for change in changes if change.action is not Action.UNCHANGED]
    ignored = gitutil.ignored_paths(repo, candidates)
    if not ignored:
        return
    print("\nwarning: these injected files are ignored by the blog repo's .gitignore:")
    for path in ignored:
        print(f"  {path.as_posix()}")
    print("They will not be committed, so the CMS and the build will not see them.")


def _print_next_steps(repo: Path, driver_configured: bool) -> None:
    print("\nnext steps")
    if not driver_configured:
        print("  - run 'fireflyer inject' again after every fresh clone:")
        print("    the merge=ours driver lives in .git/config, which is not committed")
    print("  - delete Firefly's demo content: src/content/posts/*, src/content/dynamic/*")
    print("  - set siteConfig.site_url to your domain in src/config/siteConfig.ts")
    print("  - run 'fireflyer bootstrap-vps <user@host> --base <dir>' for the server")
    print("  - add the VPS_HOST, VPS_USER, VPS_SSH_KEY and VPS_BASE repository secrets")
    print(f"  - commit and push the injected files from {repo}")


def inject_repository(
    repo: Path,
    *,
    dry_run: bool = False,
    check: bool = False,
    announce: bool = True,
) -> int:
    if not gitutil.is_repo(repo):
        raise RuntimeError(f"{repo} is not a git repository")
    context = build_context(repo)
    changes = plan(repo, context)
    pending = [change for change in changes if change.action is not Action.UNCHANGED]

    if announce:
        print(f"fireflyer inject -> {repo}\n")
    report(changes)

    if dry_run:
        print("\ndry run: nothing written")
        return 0
    if check and pending:
        print(f"\ncheck failed: {len(pending)} file(s) differ from the layer")
        return 1

    for change in pending:
        target = repo / change.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(change.payload)

    gitutil.configure_merge_driver(repo)
    _warn_ignored(repo, changes)
    if announce:
        _print_next_steps(repo, driver_configured=True)
    return 0


def run(args) -> int:
    return inject_repository(
        Path(args.repo).resolve(),
        dry_run=args.dry_run,
        check=args.check,
    )
