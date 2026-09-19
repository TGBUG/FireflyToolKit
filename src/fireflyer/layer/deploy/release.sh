#!/usr/bin/env bash
#
# Put a build output live, and keep the last few around for rollback.
#
# Run by the deploy workflow after it has rsynced a build into
# "$BASE/releases/<id>/". Also fine to run by hand:
#
#     bash release.sh 20260920120000      # deploy that release
#     bash release.sh 20260919180000      # roll back to it
#
# BASE defaults to the directory this script lives in, so the copy installed at
# $BASE/release.sh needs no arguments or environment. Override with
# FIREFLYER_BASE, and the number of releases kept with FIREFLYER_KEEP.
#
# Requires only bash and GNU coreutils -- deliberately not rsync, not python.

set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASE="${FIREFLYER_BASE:-$here}"
KEEP="${FIREFLYER_KEEP:-5}"

release="${1:?usage: release.sh <release-id>}"
dir="$BASE/releases/$release"

case "$release" in
*[!A-Za-z0-9._-]* | '' | .*)
	echo "refusing suspicious release id: $release" >&2
	exit 1
	;;
esac

if [ ! -d "$dir" ]; then
	echo "release not found: $dir" >&2
	exit 1
fi

# Swap through a temporary name. A bare `ln -sfn` removes and recreates the
# symlink in two steps, and a request can land in the gap.
if [ -e "$BASE/current" ] && [ ! -L "$BASE/current" ]; then
	echo "$BASE/current exists and is not a symlink. Move it aside and re-run." >&2
	exit 1
fi

ln -sfn "$dir" "$BASE/current.tmp"
mv -T "$BASE/current.tmp" "$BASE/current"

echo "live: $release"

# Prune, newest first -- but never the release that is currently live. Pruning
# purely by age would delete the target of a rollback: roll back to an old
# release, deploy once more, and the symlink would point at a directory that no
# longer exists, taking the site down. `current` itself lives one level up and
# is not matched here.
live="$(readlink -f "$BASE/current" 2>/dev/null || true)"
cd "$BASE/releases"
ls -1dt -- */ 2>/dev/null | tail -n +"$((KEEP + 1))" | while IFS= read -r dir; do
	name="${dir%/}"
	if [ -n "$live" ] && [ "$(readlink -f "$name")" = "$live" ]; then
		echo "keeping $name: it is live"
		continue
	fi
	echo "pruning $name"
	rm -rf -- "$name"
done

echo "kept: $(ls -1dt -- */ 2>/dev/null | wc -l)"
