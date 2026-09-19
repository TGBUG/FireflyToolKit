"""Compare the CMS config against the theme's schema, and check repository state.

Two failure modes motivate this, both of which are silent until a build breaks.

*Schema drift.* ``public/admin/config.yml`` declares the fields the CMS writes;
``src/content.config.ts`` declares what the theme accepts. A field missing from
the schema is stripped by Zod without complaint, so the CMS reports a successful
save while the value goes nowhere. A required schema field missing from the
config is worse: the CMS cannot supply it, so the build fails after publishing.

*Repository state.* Upstream ships ``build.yml`` and ``deploy.yml``, both of which
trigger on every push to the master branch. Left enabled they cost far more
Actions minutes than this project's own deploy does, so they are disabled through
the GitHub API -- state that lives outside git, and therefore outside everything
else that might drift.

The schema is read by scanning the TypeScript, not by running it: this has to
work in CI where ``node_modules`` may not exist, and the file changes rarely
enough that a small, tested scanner is a better trade than a Node dependency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from fireflyer import github, gitutil

# Fields the CMS legitimately declares that have no place in the Zod schema.
# `body` is content rather than front matter; `slug` is written by the theme's own
# new-post script and ignored by its routing (the file path is the URL);
# `_slug` is Fireflyer's own field, consumed by the `path` template.
ALLOWED_EXTRAS = {"body", "slug", "_slug"}

# Widget -> the Zod kind it should be paired with. Mismatches are warnings, not
# failures: several widgets map onto strings, and a wrong guess here should not
# block a build.
WIDGET_KINDS = {
    "string": "string",
    "text": "string",
    "markdown": "string",
    "richtext": "string",
    "image": "string",
    "file": "string",
    "select": "string",
    "color": "string",
    "code": "string",
    "hidden": "string",
    "relation": "string",
    "datetime": "date",
    "boolean": "boolean",
    "number": "number",
    "list": "array",
    "object": "object",
    "map": "object",
    "keyvalue": "object",
}

# Zod kinds worth comparing a widget against. Anything else -- `union`, `enum`,
# `literal`, `any` -- is left alone rather than guessed at.
KNOWN_KINDS = {"string", "date", "boolean", "number", "array", "object"}

KNOWN_WORKFLOWS = {"biome.yml", "build.yml", "deploy.yml", "fireflyer-deploy.yml"}
MUST_BE_DISABLED = {"build.yml", "deploy.yml"}
# GitHub registers this one dynamically from .github/dependabot.yml, so it has no
# filename of its own.
DEPENDABOT_WORKFLOW = "dependabot-updates"

_DEFINE_COLLECTION = re.compile(r"defineCollection\s*\(\s*\{")
_BASE = re.compile(r"""base:\s*["']\./src/content/([^"']+)["']""")
_SCHEMA = re.compile(r"schema:\s*")
_ZOD_OBJECT = re.compile(r"z\.object\s*\(\s*\{")
# The method name may sit on the next line: the theme writes some fields as
# `link: z\n    .array(`, so whitespace has to be allowed before the dot.
_ZOD_KIND = re.compile(r"^\s*z\s*\.\s*([A-Za-z]+)")
_FIELD = re.compile(r"^\s*([A-Za-z_$][\w$]*)\s*:\s*(.+)$", re.S)
_OPTIONAL = (".optional()", ".nullish()", ".default(")


@dataclass(frozen=True)
class Finding:
    level: str  # "error" | "warning" | "info"
    message: str


@dataclass(frozen=True)
class ZodField:
    kind: str | None
    required: bool


# --------------------------------------------------------------------------- #
# Reading the theme's TypeScript schema                                        #
# --------------------------------------------------------------------------- #


def _strip_comments(text: str) -> str:
    """Remove // and /* */ comments, leaving string literals alone."""
    out: list[str] = []
    index = 0
    quote: str | None = None
    while index < len(text):
        char = text[index]
        if quote is not None:
            out.append(char)
            if char == "\\" and index + 1 < len(text):
                out.append(text[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "\"'`":
            quote = char
            out.append(char)
            index += 1
            continue
        if char == "/" and text.startswith("//", index):
            newline = text.find("\n", index)
            if newline == -1:
                break
            index = newline
            continue
        if char == "/" and text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = len(text) if end == -1 else end + 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _matching_brace(text: str, open_index: int) -> int:
    """Index of the brace closing the one at *open_index*."""
    depth = 0
    index = open_index
    quote: str | None = None
    while index < len(text):
        char = text[index]
        if quote is not None:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "\"'`":
            quote = char
            index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise ValueError("unbalanced braces")


def _split_top_level(text: str) -> list[str]:
    """Split on commas that are not nested inside brackets or strings."""
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    index = 0
    while index < len(text):
        char = text[index]
        if quote is not None:
            current.append(char)
            if char == "\\" and index + 1 < len(text):
                current.append(text[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "\"'`":
            quote = char
            current.append(char)
        elif char in "([{":
            depth += 1
            current.append(char)
        elif char in ")]}":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    parts.append("".join(current))
    return parts


def parse_schema(path: Path) -> dict[str, dict[str, ZodField]]:
    """Map collection name -> field name -> Zod field, read from the TS source."""
    if not path.is_file():
        raise FileNotFoundError(path)
    text = _strip_comments(path.read_text(encoding="utf-8"))

    collections: dict[str, dict[str, ZodField]] = {}
    for match in _DEFINE_COLLECTION.finditer(text):
        block_start = text.index("{", match.end() - 1)
        block = text[block_start : _matching_brace(text, block_start) + 1]

        base = _BASE.search(block)
        if base is None:
            continue
        name = base.group(1)

        schema = _SCHEMA.search(block)
        if schema is None:
            collections[name] = {}
            continue
        obj = _ZOD_OBJECT.search(block, schema.end())
        if obj is None:
            collections[name] = {}
            continue
        inner_start = obj.end() - 1
        inner = block[inner_start : _matching_brace(block, inner_start) + 1]

        fields: dict[str, ZodField] = {}
        for segment in _split_top_level(inner[1:-1]):
            found = _FIELD.match(segment)
            if found is None:
                continue
            field_name, expression = found.group(1), found.group(2)
            kind_match = _ZOD_KIND.match(expression)
            fields[field_name] = ZodField(
                kind=kind_match.group(1).lower() if kind_match else None,
                required=not any(marker in expression for marker in _OPTIONAL),
            )
        collections[name] = fields
    return collections


# --------------------------------------------------------------------------- #
# Reading the CMS config                                                       #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ConfigField:
    widget: str | None
    required: bool


def parse_config(path: Path) -> dict[str, dict[str, ConfigField]]:
    """Map collection name -> field name -> declared widget, read from the YAML."""
    if not path.is_file():
        raise FileNotFoundError(path)
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    collections: dict[str, dict[str, ConfigField]] = {}
    for collection in document.get("collections") or []:
        folder = (collection.get("folder") or "").rstrip("/")
        name = folder.rsplit("/", 1)[-1] or collection.get("name")
        fields: dict[str, ConfigField] = {}
        for field in collection.get("fields") or []:
            field_name = field.get("name")
            if not field_name:
                continue
            # Nested `fields:` under a list widget describe list items, not
            # front matter keys, so they are deliberately not walked.
            fields[field_name] = ConfigField(
                widget=field.get("widget"),
                required=field.get("required", True) is not False,
            )
        collections[name] = fields
    return collections


# --------------------------------------------------------------------------- #
# Comparison                                                                   #
# --------------------------------------------------------------------------- #


def compare(
    schema: dict[str, dict[str, ZodField]],
    config: dict[str, dict[str, ConfigField]],
) -> list[Finding]:
    findings: list[Finding] = []

    for name, fields in config.items():
        if name not in schema:
            findings.append(
                Finding("error", f"collection '{name}' has no matching collection in the schema")
            )
            continue
        zod_fields = schema[name]

        for field_name, declared in fields.items():
            if field_name in ALLOWED_EXTRAS:
                continue
            if field_name not in zod_fields:
                findings.append(
                    Finding(
                        "error",
                        f"{name}.{field_name}: declared in config.yml but absent from the schema, "
                        "so the value is written and then silently dropped",
                    )
                )
                continue
            expected = WIDGET_KINDS.get(declared.widget or "")
            actual = zod_fields[field_name].kind
            if expected and actual in KNOWN_KINDS and expected != actual:
                findings.append(
                    Finding(
                        "warning",
                        f"{name}.{field_name}: widget '{declared.widget}' implies {expected} "
                        f"but the schema declares {actual}",
                    )
                )

        for field_name, zod_field in zod_fields.items():
            if not zod_field.required or field_name in fields:
                continue
            findings.append(
                Finding(
                    "error",
                    f"{name}.{field_name}: required by the schema but not declared in config.yml, "
                    "so the CMS cannot supply it and the build will fail",
                )
            )

        for field_name, declared in fields.items():
            if field_name in ALLOWED_EXTRAS or field_name not in zod_fields:
                continue
            if zod_fields[field_name].required and not declared.required:
                findings.append(
                    Finding(
                        "error",
                        f"{name}.{field_name}: required by the schema but marked required:false "
                        "in config.yml, so the CMS will let it be saved empty",
                    )
                )

    return findings


# --------------------------------------------------------------------------- #
# Repository state                                                             #
# --------------------------------------------------------------------------- #


def check_repo_state(repo: Path) -> list[Finding]:
    findings: list[Finding] = []

    workflows = repo / ".github" / "workflows"
    if workflows.is_dir():
        for path in sorted(workflows.glob("*.yml")) + sorted(workflows.glob("*.yaml")):
            if path.name not in KNOWN_WORKFLOWS:
                findings.append(
                    Finding("warning", f".github/workflows/{path.name}: unexpected workflow")
                )

    slug = gitutil.remote_slug(repo)
    auth = github.token()
    if not slug or not auth:
        findings.append(
            Finding(
                "info",
                "skipped the GitHub workflow check: "
                + ("no origin remote" if not slug else "set GH_TOKEN to enable it"),
            )
        )
        return findings

    try:
        branch = github.default_branch(slug, auth)
        states = github.workflow_states(slug, auth)
    except github.GitHubError as error:
        findings.append(Finding("warning", f"could not read repository state from GitHub: {error}"))
        return findings

    if branch is not None and branch != "master":
        findings.append(
            Finding(
                "warning",
                f"the default branch is '{branch}', not 'master'. Set it to master in the "
                "repository settings so clones, the Actions tab, and this check all agree.",
            )
        )

    if not states:
        # Expected on a repository that has never received a push: GitHub
        # registers workflows when work first arrives on a branch, so straight
        # after mirroring the list is empty. It is still worth saying, because an
        # empty list means the theme's CI could not be checked at all.
        findings.append(
            Finding(
                "warning",
                f"GitHub reports no workflows for {slug}, so the theme's build.yml and "
                "deploy.yml could not be checked. This is normal before the repository's "
                "first push -- workflows register once work lands on a branch. Push, then "
                "re-run this check.",
            )
        )
        return findings

    for name in sorted(MUST_BE_DISABLED):
        state = states.get(name)
        if state is None:
            findings.append(
                Finding(
                    "warning",
                    f"{name} is not registered with GitHub, so it could not be checked. "
                    "Upstream may have renamed or removed it.",
                )
            )
        elif state != "disabled_manually":
            findings.append(
                Finding(
                    "error",
                    f"{name} is enabled ({state}). It triggers on every push to master and costs "
                    "far more Actions minutes than the deploy itself. Disable it with: "
                    f"gh workflow disable {name}",
                )
            )

    # Dependabot is a judgement call rather than an error: measured on a real
    # repository it billed ten minutes in a single run, five times this project's
    # own deploy. On a blog that follows a theme upstream, the dependency PRs it
    # opens are mostly noise, since upstream makes those same updates.
    if states.get(DEPENDABOT_WORKFLOW) not in (None, "disabled_manually"):
        findings.append(
            Finding(
                "warning",
                f"{DEPENDABOT_WORKFLOW} is enabled. A single run measured ten billed minutes, "
                "against two for the deploy itself. Turn Dependabot version updates off in the "
                "repository's security settings unless you want to track the theme's "
                "dependencies yourself.",
            )
        )
    return findings


# --------------------------------------------------------------------------- #
# Entry point                                                                  #
# --------------------------------------------------------------------------- #

_ORDER = {"error": 0, "warning": 1, "info": 2}


def drift_findings(repo: Path) -> list[Finding]:
    schema = parse_schema(repo / "src" / "content.config.ts")
    config = parse_config(repo / "public" / "admin" / "config.yml")
    findings = compare(schema, config)
    findings.extend(check_repo_state(repo))
    return sorted(findings, key=lambda finding: _ORDER[finding.level])


def run(args) -> int:
    repo = Path(args.repo).resolve()
    if not gitutil.is_repo(repo):
        raise RuntimeError(f"{repo} is not a git repository")

    findings = drift_findings(repo)
    print(f"fireflyer drift-check -> {repo}\n")
    for finding in findings:
        print(f"  {finding.level:<8} {finding.message}")

    errors = [finding for finding in findings if finding.level == "error"]
    if not findings:
        print("  no drift")
    print(f"\n{len(errors)} error(s), {len(findings) - len(errors)} other finding(s)")
    return 1 if errors else 0
