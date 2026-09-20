#!/usr/bin/env bash
#
# ftk.sh — set up a new Firefly blog, run once, on the machine that will serve it.
#
#     curl -fsSL https://raw.githubusercontent.com/TGBUG/FireflyToolKit/master/ftk.sh -o ftk.sh
#     bash ftk.sh
#
# It asks for the repository, a token, and where releases should live, and then:
#
#   1. copies Firefly's history into the repository, pushing `master` on its own
#      first so it becomes the repository's default branch
#   2. writes the toolkit's files into it and pushes
#   3. disables the theme's own build.yml and deploy.yml, which would otherwise
#      trigger on every push and cost far more Actions minutes than deploying
#   4. creates the release directory, the `current` symlink and release.sh here
#
# What it deliberately does not do: touch nginx, TLS or user accounts (a hosting
# panel owns those, and would overwrite anything written behind its back), set
# the repository's secrets (the GitHub API wants them sealed with libsodium,
# which shell cannot do), or leave anything behind. The working tree is a
# temporary directory that is removed on exit, and the token is never written to
# disk, never passed as an argument, and cleared from the environment before the
# script returns.
#
# Requires bash, git, curl and tar. No Python, no Node, no jq.
#
# Overridable for testing:
#   FTK_TOKEN      skip the token prompt
#   FTK_SLUG       skip the repository prompt
#   FTK_BASE       skip the base-directory prompt
#   FTK_REPO       the toolkit repository to fetch layer/ from
#   FTK_UPSTREAM   the theme repository to mirror

set -euo pipefail

UPSTREAM="${FTK_UPSTREAM:-https://github.com/CuteLeaf/Firefly.git}"
TOOLKIT="${FTK_REPO:-https://github.com/TGBUG/FireflyToolKit.git}"
API=https://api.github.com
UPSTREAM_CI=(build.yml deploy.yml)

say() { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
fail() {
	printf 'error: %s\n' "$*" >&2
	exit 1
}

for tool in git curl tar; do
	command -v "$tool" >/dev/null 2>&1 || fail "$tool is required but not installed"
done

# ---------------------------------------------------------------------------
# What we need to know
# ---------------------------------------------------------------------------

if [ -z "${FTK_SLUG:-}" ]; then
	printf 'blog repository (owner/name): '
	read -r FTK_SLUG
fi
[ -n "${FTK_SLUG:-}" ] || fail 'a repository is required'
case "$FTK_SLUG" in
*/*) : ;;
*) fail "expected owner/name, got '$FTK_SLUG'" ;;
esac

if [ -z "${FTK_TOKEN:-}" ]; then
	printf 'access token (Contents, Actions and Workflows, for that repository): '
	read -rs FTK_TOKEN
	printf '\n'
fi
[ -n "${FTK_TOKEN:-}" ] || fail 'a token is required'

if [ -z "${FTK_BASE:-}" ]; then
	printf 'release directory [%s/fireflyer]: ' "$HOME"
	read -r FTK_BASE
	FTK_BASE="${FTK_BASE:-$HOME/flyflyer}"
fi
case "$FTK_BASE" in
/*) : ;;
*) fail "the release directory must be an absolute path, got '$FTK_BASE'" ;;
esac

TOKEN="$FTK_TOKEN"
unset FTK_TOKEN
export GH_TOKEN="$TOKEN"

WORK="$(mktemp -d)"
cleanup() {
	rm -rf "$WORK"
	unset GH_TOKEN TOKEN
}
trap cleanup EXIT INT TERM

# git authenticates through the environment so the token never reaches argv,
# where every user on the box could read it out of `ps`.
GIT_AUTH=(-c "credential.helper=!f() { echo username=x-access-token; echo password=\$GH_TOKEN; }; f")

# curl is the same story: its options come from a file rather than the argument
# list, for the same reason.
umask 077
CURLRC="$WORK/curlrc"
printf 'header = "Authorization: Bearer %s"\n' "$TOKEN" >"$CURLRC"

api() {
	curl -fsS --config "$CURLRC" \
		-H 'Accept: application/vnd.github+json' \
		-H 'X-GitHub-Api-Version: 2022-11-28' "$@"
}

# A mirror contains the theme's .github/workflows, and GitHub will not let a
# token create or update anything there without the Workflows permission. Git's
# own message names the scope but not the remedy, so name the remedy here.
push_to() {
	local repo="$1"
	shift
	if git -C "$repo" "${GIT_AUTH[@]}" push --quiet "$@"; then
		return 0
	fi
	{
		echo
		echo "pushing to $FTK_SLUG was rejected."
		echo
		echo "If git mentioned a 'workflow' scope, the token is missing the Workflows"
		echo "permission. GitHub refuses to let a token create or update anything under"
		echo ".github/workflows without it, and a mirror contains the theme's workflows."
		echo "Add 'Workflows: read and write' to the token and run this again."
		echo
		echo "Nothing was pushed, so the repository is still empty and can be reused."
	} >&2
	exit 1
}

# ---------------------------------------------------------------------------
# 1. Only an empty repository, so nothing can be clobbered
# ---------------------------------------------------------------------------

step "checking $FTK_SLUG"

# Not "must be empty". A run that stopped part-way leaves the theme's history
# behind, and re-running should simply work, so the test is whether a setup has
# already been written here. Git is the backstop for everything else: pushing
# over commits we do not have is refused as non-fast-forward, and nothing is
# lost.
setup_code="$(curl -sS --config "$CURLRC" -o /dev/null -w '%{http_code}' \
	"$API/repos/$FTK_SLUG/contents/.node-version")"
case "$setup_code" in
404) say '  no setup here yet' ;;
200)
	fail "$FTK_SLUG already contains a FireflyToolKit setup. Point this at a different repository."
	;;
*)
	fail "cannot inspect $FTK_SLUG: GitHub answered $setup_code. Check the name, and that the token is authorised for it. A fine-grained token grants access repository by repository, so a repository that was deleted and recreated -- even under the same name -- has to be added to the token again."
	;;
esac

# ---------------------------------------------------------------------------
# 2. Mirror the theme, master first
# ---------------------------------------------------------------------------

URL="https://github.com/$FTK_SLUG.git"

step 'fetching the theme'
git clone --bare --quiet "$UPSTREAM" "$WORK/upstream"

# The whole thing is assembled locally and pushed once, at the end. That is what
# makes a failure recoverable: nothing reaches the repository until everything
# is ready, so a re-run is simply a re-run. An earlier version pushed the mirror
# first and wrote the files afterwards, which left a repository that was neither
# empty nor finished when the second half failed.
step 'writing the toolkit files'
git clone --quiet "$WORK/upstream" "$WORK/blog"
git -C "$WORK/blog" remote set-url origin "$URL"

git clone --depth 1 --quiet "$TOOLKIT" "$WORK/toolkit"
[ -d "$WORK/toolkit/layer" ] || fail "the toolkit repository has no layer/ directory"

cp -R "$WORK/toolkit/layer/." "$WORK/blog/"
git -C "$WORK/blog" status --short | sed 's/^/  /'

git -C "$WORK/blog" add -A
git -C "$WORK/blog" -c user.name=FireflyToolKit -c user.email=noreply@localhost \
	commit --quiet -m 'chore: set up FireflyToolKit'

# master alone, and only master. The first ref pushed into an empty repository
# becomes its default branch, and the theme's other thirteen branches are feature
# branches that mean nothing to a blog. Measured: pushing every branch at once
# lets GitHub choose the default, and it does not choose master.
step 'pushing to your repository (about 130 MB)'
push_to "$WORK/blog" origin master
git -C "$WORK/upstream" "${GIT_AUTH[@]}" push --quiet --tags "$URL" ||
	say '  (tags were not pushed; the blog does not need them)'
say "  pushed to $FTK_SLUG"

# ---------------------------------------------------------------------------
# 4. Stop the theme's own CI
# ---------------------------------------------------------------------------
#
# Disabling is repository state, not file state, so it survives merges. It has
# to happen after the push, because that is when GitHub registers the workflows.

step "disabling the theme's own workflows"
for name in "${UPSTREAM_CI[@]}"; do
	code="$(curl -sS --config "$CURLRC" -o /dev/null -w '%{http_code}' \
		-X PUT "$API/repos/$FTK_SLUG/actions/workflows/$name/disable")"
	case "$code" in
	204) say "  $name disabled" ;;
	404) say "  $name not registered, nothing to disable" ;;
	*) say "  $name could not be disabled (HTTP $code) -- check it in the Actions tab" ;;
	esac
done

# Disabling does not stop runs the push already queued, and those are exactly
# the minutes this is about. Cancel them, scoped per workflow so our own deploy
# is never touched. Best effort: a run that starts in the moments between the
# push and the disable can still get going, so the first setup may cost a few
# minutes regardless.
cancelled=0
for name in "${UPSTREAM_CI[@]}"; do
	for state in in_progress queued; do
		# The response is pretty-printed, so collapse whitespace before slicing it.
		# Querying per workflow is what keeps this from touching our own deploy:
		# a wrong id in the list can only 404.
		ids="$(api "$API/repos/$FTK_SLUG/actions/workflows/$name/runs?status=$state&per_page=100" |
			tr -d ' \n' | sed 's/.*"workflow_runs":\[//' |
			grep -o '"id":[0-9]*' | cut -d: -f2 || true)"
		for id in $ids; do
			curl -sS --config "$CURLRC" -o /dev/null \
				-X POST "$API/repos/$FTK_SLUG/actions/runs/$id/cancel" || true
			cancelled=$((cancelled + 1))
		done
	done
done
if [ "$cancelled" -gt 0 ]; then
	say "  cancelled $cancelled run(s) the push had started"
fi

# ---------------------------------------------------------------------------
# 5. Prepare this machine to receive releases
# ---------------------------------------------------------------------------

step "preparing $FTK_BASE"
mkdir -p "$FTK_BASE/releases"

# The symlink needs a valid target before the first deploy, or the site 404s
# from the moment the panel site exists. This placeholder is the oldest release,
# so the retention rule prunes it once real ones arrive.
if [ ! -e "$FTK_BASE/current" ]; then
	placeholder="$FTK_BASE/releases/00000000000000"
	mkdir -p "$placeholder"
	cat >"$placeholder/index.html" <<'HTML'
<!doctype html>
<html lang="en"><head><meta charset="utf-8" /><title>Not deployed yet</title></head>
<body><p>No release has been deployed to this site yet.</p></body></html>
HTML
	ln -s "$placeholder" "$FTK_BASE/current"
	say "  current -> 00000000000000"
else
	say '  kept the existing current symlink'
fi

install -m 755 "$WORK/blog/deploy/release.sh" "$FTK_BASE/release.sh"
say '  installed release.sh'

# ---------------------------------------------------------------------------
# 6. What is left, which is manual on purpose
# ---------------------------------------------------------------------------

cat <<EOF

setup is done. what remains:

  1. in your hosting panel, create the site for your domain with its document
     root set to:
         $FTK_BASE/current
     and issue TLS for it from the panel. Do not edit nginx by hand: the panel
     owns that file and will overwrite it.

  2. in $FTK_SLUG, add four repository secrets
     (Settings -> Secrets and variables -> Actions):
         VPS_HOST       the hostname or IP you use to reach this server -- not
                        this machine's own hostname, which is usually an
                        internal name the runner cannot resolve
         VPS_USER       $(id -un)
         VPS_SSH_KEY    the private key that can log in as $(id -un)
         VPS_BASE       $FTK_BASE

     setup pushed the toolkit's files, and the deploy workflow has already run
     once and failed, because those secrets did not exist yet. Re-run it from
     the Actions tab when they do.

  3. delete the theme's demo content, so it is not published:
         src/content/posts/     (all of the sample posts)
         src/content/dynamic/   (the sample moments)
     and delete .github/dependabot.yml -- the theme configures Dependabot to run
     daily, which measured ten billed Actions minutes per run, five times what
     deploying costs.

  4. set siteConfig.site_url in src/config/siteConfig.ts to your domain.

Then write at https://<your-domain>/admin/, signing in with a token that has
Contents, Pull requests and Issues access to $FTK_SLUG.
EOF
