#!/usr/bin/env bash
#
# Merge theme updates from upstream while keeping this blog's own content.
#
#     bash scripts/fireflytoolkit-merge-upstream.sh [branch]
#
# Three things have to end up on our side of the merge, and none of them is the
# default:
#
#   * `src/content/` is this blog's content. Where upstream edited the same file,
#     ours wins.
#   * `public/gallery/` is where album photos live. The theme scans that
#     directory at build time, so it is not a path that could be moved somewhere
#     safer -- and it ships with two demo albums, which setup deletes. Upstream
#     edits to those have to stay deleted.
#   * `.github/dependabot.yml` was deleted on purpose during setup: the theme
#     configures Dependabot for a daily run, which costs far more Actions minutes
#     than deploying the blog does. If upstream ever edits that file, the
#     deletion has to stay a deletion.
#
# `git merge -X ours` is deliberately NOT used. It would apply to every conflict,
# including the ones under `src/config/`, where a theme update is adding
# configuration options we do want. Those are left for you to resolve.
#
# One case is worth naming, because it is the one that actually happens: upstream
# editing a demo post, or a demo album photo, that this blog deleted. Git reports that as a modify/delete
# conflict, never consults a merge driver, and -- measured against git 2.45 --
# leaves upstream's copy in the tree, so the demo post silently returns. It is
# resolved explicitly below.

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
if ! git merge --no-edit "upstream/$branch"; then
	while IFS= read -r path; do
		[ -n "$path" ] || continue
		case "$path" in
		src/content/* | public/gallery/* | .github/dependabot.yml)
			if git cat-file -e "HEAD:$path" 2>/dev/null; then
				echo "keeping ours:     $path"
				git checkout --ours -- "$path"
				git add -- "$path"
			else
				echo "keeping deletion: $path"
				git rm -q --ignore-unmatch -- "$path"
			fi
			;;
		esac
	done <<<"$(git diff --name-only --diff-filter=U)"

	if git diff --name-only --diff-filter=U | grep -q .; then
		{
			echo
			echo "these conflicts are yours to resolve:"
			git diff --name-only --diff-filter=U
			echo
			echo "src/config/ conflicts are expected -- a theme update is adding options."
			echo "resolve them, then 'git add' and 'git commit'."
		} >&2
		exit 1
	fi

	git commit --no-edit
	echo "merged, with content and deletions preserved"
fi

# An addition conflicts with nothing, so it would land quietly and be published.
added="$(git diff --name-only --diff-filter=A "$before" HEAD -- src/content/ || true)"
if [ -n "$added" ]; then
	echo
	echo "the update added these under src/content/ -- review before pushing:"
	while IFS= read -r path; do
		[ -n "$path" ] && echo "  $path"
	done <<<"$added"
	echo "remove them with 'git rm' if they are demo content you do not want."
fi

echo
echo "next: pnpm install && pnpm dev, then push."
