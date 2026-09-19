"""Prepare a server to receive deploys.

Deliberately narrow. The host runs a web hosting panel that owns nginx and TLS,
rewrites a site's configuration whenever the operator touches it from the UI, and
does its own certificate renewal. Fireflyer does not install nginx configuration,
does not run Certbot, and does not create users -- anything it wrote in those
areas would either be overwritten by the panel or fight it. See ADR-0006.

What is left is the part nothing else can do: create the directory layout, give
the `current` symlink something valid to point at before the first deploy, and
install the release script.

Everything runs over a single `ssh ... bash -s`, so the remote needs nothing
beyond bash and coreutils. The deploy workflow adds `tar`. Neither needs rsync,
Python or scp, and a server managed by a hosting panel may not have them.
"""

from __future__ import annotations

import re
import subprocess
import sys
from importlib.resources import files

_WINDOWS_PATH = re.compile(r"^[A-Za-z]:")

RELEASE_SCRIPT = ("layer", "deploy", "release.sh")
PLACEHOLDER_RELEASE = "00000000000000"
_EOF = "__FIREFLYER_RELEASE_SCRIPT__"
_PLACEHOLDER_EOF = "__FIREFLYER_PLACEHOLDER__"

MANUAL_STEPS = """\
manual steps, on purpose -- Fireflyer does not do these
  - create the deploy user, and install its public key in that user's
    authorized_keys. It only needs write access to {base}
  - in the hosting panel: create the site for your domain, with its document
    root set to {base}/current
  - issue TLS for that domain from the panel; it renews it for you afterwards
  - in the blog repository: add the VPS_HOST, VPS_USER, VPS_SSH_KEY and
    VPS_BASE secrets
"""


def release_script_text() -> str:
    script = files("fireflyer")
    for part in RELEASE_SCRIPT:
        script = script / part
    if not script.is_file():
        raise RuntimeError("deploy/release.sh is missing from the installed package")
    return script.read_text(encoding="utf-8")


def remote_script(base: str) -> str:
    """The whole remote body, as one bash script."""
    script = release_script_text()
    if _EOF in script or _PLACEHOLDER_EOF in script:
        raise RuntimeError("the release script contains a heredoc delimiter")

    return f"""\
set -euo pipefail

BASE={base}

mkdir -p "$BASE/releases"

# The symlink has to point somewhere before the first deploy, or the site 404s
# from the moment the panel site is created. This placeholder is the oldest
# release, so the retention rule prunes it once real ones exist.
if [ ! -e "$BASE/current" ]; then
	mkdir -p "$BASE/releases/{PLACEHOLDER_RELEASE}"
	cat > "$BASE/releases/{PLACEHOLDER_RELEASE}/index.html" <<'{_PLACEHOLDER_EOF}'
<!doctype html>
<html lang="en">
	<head><meta charset="utf-8" /><title>Not deployed yet</title></head>
	<body><p>No release has been deployed to this site yet.</p></body>
</html>
{_PLACEHOLDER_EOF}
	if [ -e "$BASE/current" ] || [ -L "$BASE/current" ]; then
		echo "refusing to replace an existing $BASE/current" >&2
		exit 1
	fi
	ln -s "$BASE/releases/{PLACEHOLDER_RELEASE}" "$BASE/current"
	echo "created $BASE/current -> {PLACEHOLDER_RELEASE}"
else
	echo "kept existing $BASE/current"
fi

cat > "$BASE/release.sh" <<'{_EOF}'
{script}{_EOF}
chmod +x "$BASE/release.sh"
echo "installed $BASE/release.sh"

echo
echo "layout:"
ls -la "$BASE"
"""


def run(args) -> int:
    base = args.base.rstrip("/")
    if not base.startswith("/"):
        print(
            "--base must be an absolute POSIX path: it is used on the server, not "
            f"on this machine. Got {args.base!r}.",
            file=sys.stderr,
        )
        if _WINDOWS_PATH.match(base):
            print(
                "That looks like a Windows path. From Git Bash, MSYS rewrites arguments "
                "that look like POSIX paths; prefix the command with MSYS_NO_PATHCONV=1 "
                "to stop it.",
                file=sys.stderr,
            )
        return 2

    script = remote_script(base)

    if args.print_only:
        # The script goes to stdout so it can be piped straight into ssh; the
        # notes go to stderr so they do not end up inside the script.
        print(script)
        print(MANUAL_STEPS.format(base=base), file=sys.stderr)
        return 0

    print(f"fireflyer bootstrap-vps -> {args.target}:{base}\n", flush=True)
    command = ["ssh", "-p", str(args.port)]
    if args.identity:
        # IdentitiesOnly keeps ssh from trying every agent key first, which on a
        # server with a low MaxAuthTries logs a failure before the right one.
        command += ["-i", args.identity, "-o", "IdentitiesOnly=yes"]
    command += ["-o", "StrictHostKeyChecking=accept-new", args.target, "bash", "-s"]

    # Bytes, not text. With text=True Python writes stdin through a text wrapper
    # whose newline translation turns every \n into os.linesep, so on Windows the
    # remote receives "set -euo pipefail\r" and bash rejects the option name.
    # The remote is a POSIX shell and wants LF, whatever this machine uses.
    result = subprocess.run(command, input=script.encode("utf-8"))
    if result.returncode != 0:
        print("\nbootstrap failed; nothing else was changed", file=sys.stderr)
        return result.returncode

    print()
    print(MANUAL_STEPS.format(base=base))
    return 0
