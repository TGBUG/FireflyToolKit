# The layer only adds paths, and is copied in by name

FireflyToolKit delivers its value by copying files into a blog repo, not by being a git remote of it. Its history is unrelated to Firefly's, so `git pull` from it fails with unrelated histories; making that work would require FireflyToolKit to be a fork of Firefly, turning every theme update into a two-hop merge. So the files live at `layer/` mirroring a blog repository's root, and `ftk.sh` copies them across with `cp -R`.

Every filename in the layer is one Firefly does not ship:

```
public/admin/index.html
public/admin/config.json
public/admin/sveltia-cms.js
public/admin/chunks/react-dom.js
.github/workflows/fireflytoolkit-deploy.yml
.github/scripts/check-schema.mjs
deploy/release.sh
scripts/fireflytoolkit-merge-upstream.sh
.node-version
FIREFLYTOOLKIT.md
```

Two corrections to earlier versions of that list are worth keeping. It is **filenames, not directories**: Firefly ships `.github/workflows/build.yml` and `deploy.yml` already, so a layer file called `deploy.yml` would overwrite a shipped one and conflict on every upstream merge — hence `fireflytoolkit-deploy.yml`. And the theme ships its own root `.gitattributes`, so a layer `.gitattributes` is not a free path either.

## Which copy wins

An earlier version of this decision had the tool double as the runtime source of truth: re-injecting would overwrite whatever a blog repo had, on the theory that drift between the two was the thing to prevent. That is no longer how it works, and the reason is the tool's shape.

The tool runs once, at setup, on the server — and then it is gone. There is no second `inject` to reconcile anything with. What exists afterwards is a blog repo holding a copy of the layer, which the owner is free to edit: the deploy workflow, the merge script, the CMS config. Those edits are the point, not drift, and there is nothing to overwrite them. A later re-run of `ftk.sh` refuses to touch a repository that already has branches, so it cannot silently revert them either.

The one thing that *is* checked after setup is the pair that fails quietly: `config.json` against the theme's Zod schema, in the deploy workflow, before the build. See ADR-0009.

## The content protection that used to live here

The layer previously carried `src/content/.gitattributes` marking content `merge=ours`, paired with a `merge.ours` driver written into the blog repo's `.git/config`. Both are gone.

The driver had a worse problem than its cost. It only runs for a file present on both sides, so it did nothing for the case that actually occurs — upstream editing a demo post this blog deleted. Git reports that as a modify/delete conflict, never consults the driver, and (measured against git 2.45) leaves upstream's copy in the tree, so the deleted post comes back. `git merge -X ours` behaves identically.

Worse, the driver was **machine-local state**: `.git/config` is never committed, so every fresh clone had the attribute and no working driver, and the documented remedy was to re-run the tool. That is what made the tool look like something with a lifecycle rather than a one-shot setup step.

`scripts/fireflytoolkit-merge-upstream.sh` now handles both cases explicitly, at the moment they matter, and needs nothing on the machine beforehand: content conflicts resolve to ours, deliberate deletions stay deletions, and `src/config/` conflicts are left for the human because those are a theme update offering new options. `-X ours` is deliberately not used, since it would swallow that last category too.
