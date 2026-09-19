"""Command-line entry point for Fireflyer."""

from __future__ import annotations

import argparse
import sys

from fireflyer import __version__

UPSTREAM_URL = "https://github.com/CuteLeaf/Firefly.git"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fireflyer",
        description="Turn a stock Firefly Astro blog into a browser-editable, self-hosted site.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subcommands = parser.add_subparsers(dest="command", metavar="<command>")

    onboard = subcommands.add_parser(
        "init",
        help="onboard an empty GitHub repository: mirror Firefly, inject, disable the theme's CI",
    )
    onboard.add_argument("repo", help="the empty repository, as owner/name")
    onboard.add_argument(
        "--dir",
        help="where to put the working clone (default: ./<repository name>)",
    )
    onboard.add_argument(
        "--upstream",
        default=UPSTREAM_URL,
        help="upstream Firefly URL (default: %(default)s)",
    )
    onboard.add_argument(
        "--no-disable-upstream-ci",
        action="store_true",
        help="skip disabling upstream's build.yml and deploy.yml through the GitHub API",
    )

    inject = subcommands.add_parser(
        "inject",
        help="write the injected layer into a blog repository",
    )
    inject.add_argument("repo", help="path to the blog repository")
    inject.add_argument("--dry-run", action="store_true", help="print the plan without writing")
    inject.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if anything would change, without writing",
    )

    drift = subcommands.add_parser(
        "drift-check",
        help="compare the CMS config against the theme's Zod schema and check repository state",
    )
    drift.add_argument("repo", help="path to the blog repository")

    bootstrap = subcommands.add_parser(
        "bootstrap-vps",
        help="prepare a server to receive deploys (does not touch nginx or TLS)",
    )
    bootstrap.add_argument("target", help="user@host of the server")
    bootstrap.add_argument(
        "--base",
        required=True,
        help="absolute directory on the server that will hold releases and the current symlink",
    )
    bootstrap.add_argument("--port", default="22", help="SSH port (default: %(default)s)")
    bootstrap.add_argument(
        "--identity",
        help="private key to authenticate with; omit to use the ssh defaults",
    )
    bootstrap.add_argument(
        "--print-only",
        action="store_true",
        help="print the remote script instead of running it",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    # Imported lazily so that --help works without every module's dependencies present.
    match args.command:
        case "init":
            from fireflyer import onboard

            return onboard.run(args)
        case "inject":
            from fireflyer import inject

            return inject.run(args)
        case "drift-check":
            from fireflyer import drift

            return drift.run(args)
        case "bootstrap-vps":
            from fireflyer import bootstrap

            return bootstrap.run(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
