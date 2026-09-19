# The additive layer only adds paths, and is injected idempotently

Fireflyer delivers value by copying files into a blog repo, not by being a git remote of it. Fireflyer's history is unrelated to Firefly's, so `git pull fireflyer` fails with unrelated histories; making it work would require Fireflyer itself to be a fork of Firefly, turning every theme update into a two-hop merge. So the layer is stored at `src/fireflyer/layer/` mirroring a blog repository's root, and `inject` copies it across. Dotfiles are stored un-dotted and renamed on the way in, so that neither git nor the packaging tooling has to reason about them.

Every injected filename is one Firefly does not ship:

```
public/admin/index.html
public/admin/config.yml
public/admin/sveltia-cms.js
public/admin/chunks/react-dom.js
.github/workflows/fireflyer-deploy.yml
deploy/release.sh
scripts/fireflyer-merge-upstream.sh
src/content/.gitattributes
FIREFLYER.md
.node-version
```

Two corrections to earlier versions of that list are worth keeping. It is **filenames, not directories**: Firefly ships `.github/workflows/build.yml` and `deploy.yml` already, so a layer file called `deploy.yml` would overwrite a shipped one and conflict on every upstream merge — hence `fireflyer-deploy.yml`. And `.gitattributes` is not free either: Firefly ships one at the repository root holding `* text=auto eol=lf`, so the content protection lives at `src/content/.gitattributes`, which upstream does not have and which is also more precise about what it covers.

## What protecting `src/content/` actually buys

`src/content/.gitattributes` marks the content directory `merge=ours`, and `inject` defines that driver in the blog repo's `.git/config`. Both halves are required: the attribute names the driver, and the driver has to be repo-local because `.git/config` is never committed. A fresh clone therefore has the attribute and no working driver until `inject` runs again — which is why every run ends by saying so, and why `drift-check` reports a missing driver.

The protection is **narrower than an earlier draft claimed**. A merge driver only runs for a file that exists on both sides with conflicting content. When a theme update edits a demo post this blog deleted — the case that actually happens during setup — git raises a `modify/delete` conflict, never consults the driver, and leaves upstream's copy in the tree, so the deleted post silently returns. `git merge -X ours` was measured against git 2.45 and behaves identically. So `scripts/fireflyer-merge-upstream.sh` resolves those conflicts explicitly, and separately reports any file upstream *added* under `src/content/` — an addition conflicts with nothing, and would otherwise be published without anyone noticing.

Files under `src/config/` are deliberately left unprotected. Theme updates add configuration keys there, and those changes should land.

## The two things that drift

`drift-check` covers both, because both fail silently.

**Schema drift.** `config.yml` and the Zod schema in `src/content.config.ts` can diverge. A field the schema does not know is stripped by Zod without complaint, so the CMS reports a successful save and the value goes nowhere. In the other direction, a schema-required field the config never declares cannot be supplied by the CMS at all, and the build fails only after an entry is published. This is checked rather than prevented by a shared source of truth, because the single-source packages (`@pattform/cms-kit`, `astro-loader-sveltia-cms`) modify `astro.config.mjs` and `src/content.config.ts` — the two files Firefly's own update guide warns against touching.

**Repository state.** Firefly's `build.yml` (`astro check` and `astro build`, across a Node 22/23 matrix) and `deploy.yml` (a full build plus a GitHub Pages deploy) both trigger on every push to `master`, costing far more runner time than this project's own deploy. `init` disables both through the GitHub API, which is repository state rather than file state and so survives upstream merges. Because upstream can later add a workflow that arrives enabled, `drift-check` reads the workflow list back from the API and reports anything unexpected or re-enabled.
