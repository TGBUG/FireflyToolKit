#!/usr/bin/env bash
#
# Merge theme updates from upstream while keeping this blog's own content.
#
#     bash scripts/fireflyer-merge-upstream.sh [branch]
#
# Why this exists instead of a plain `git merge upstream/master`:
#
# `src/content/.gitattributes` marks this blog's content as `merge=ours`, which
# settles the case where both sides edited the same file. It does nothing for
# the case that actually bites: a theme update editing a demo post that this
# blog deleted. Git reports that as a modify/delete conflict, never consults the
# merge driver, and -- verified against git 2.45 -- leaves upstream's copy in the
# tree, so the demo post silently comes back. `git merge -X ours` does not help;
# it produces the same conflict. So that case is resolved here, explicitly.
#
# Files under src/config/ are deliberately NOT forced to ours. Theme updates add
# configuration keys there and those changes should land; conflicts in that
# directory are expected and are for you to resolve by hand.

set -euo pipefail

branch="${1:-master}"

if ! git remote get-url upstream >/dev/null 2>&1; then
	echo "no 'upstream' remote. Add one with:" >&2
	echo "    git remote add upstream https://github.com/CuteLeaf/Firefly.git" >&2
	exit 1
fi

git fetch upstream
before="$(git rev-parse HEAD)"

echo "merging upstream/$branch"
if git merge --no-edit "upstream/$branch"; then
	echo "merged cleanly"
else
	# Unmerged paths where our side deleted the file: keep the deletion.
	unmerged="$(git diff --name-only --diff-filter=U -- src/content/ || true)"
	if [ -n "$unmerged" ]; then
		while IFS= read -r path; do
			[ -n "$path" ] || continue
			if git cat-file -e "HEAD:$path" 2>/dev/null; then
				continue # still exists on our side: a real content conflict
			fi
			echo "keeping our deletion: $path"
			git rm -q --ignore-unmatch -- "$path"
		done <<<"$unmerged"
	fi

	if git diff --name-only --diff-filter=U | grep -q .; then
		echo >&2
		echo "conflicts left for you to resolve:" >&2
		git diff --name-only --diff-filter=U >&2
		echo >&2
		echo "resolve them, then 'git add' and 'git commit'." >&2
		exit 1
	fi

	git commit --no-edit
	echo "merged, with content deletions preserved"
fi

# A theme update can ADD demo content rather than edit it, and additions never
# conflict, so they would quietly land in the content directory and be
# published. Report them instead.
added="$(git diff --name-only --diff-filter=A "$before" HEAD -- src/content/ || true)"
if [ -n "$added" ]; then
	echo
	echo "upstream added these files under src/content/ -- review before pushing:"
	while IFS= read -r path; do
		[ -n "$path" ] && echo "  $path"
	done <<<"$added"
	echo "delete them with 'git rm' if they are demo content you do not want."
fi

echo
echo "next: pnpm install && pnpm dev, then push."
