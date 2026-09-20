# FireflyToolKit

One script that turns a stock Firefly Astro blog into a self-hosted, browser-editable site. It is run once, on the machine that will serve the blog, and leaves behind a blog repository and a prepared server rather than a running system.

## Language

### Repositories

**Firefly**:
The upstream Astro blog theme at `CuteLeaf/Firefly` (public). Consumed and merged from, never modified.
_Avoid_: 主题仓库, theme repo

**FireflyToolKit**:
This repository. The single source of truth for everything written into a blog repo, delivered as `ftk.sh` plus `layer/`.
_Avoid_: Fireflyer, 系统, 平台, backend, 服务端, 编写端

**Blog repo**:
A private repository holding one blog instance — Firefly's source, that blog's content, and the layer. Produced by mirroring, not forking.
_Avoid_: 博客原仓库, 内容仓库, fork

**Upstream**:
Firefly as reached from a blog repo, via a git remote named `upstream`. The channel through which theme updates arrive. Per-clone, so a fresh clone has to add it.

**Layer**:
The files under `layer/` that get copied into a blog repo. Every filename in it is one Firefly does not ship.
_Avoid_: 附加层, overlay, patch, inject

### Content

**Collection**:
One of Firefly's four content types, declared in `src/content.config.ts`: `posts`, `dynamic`, `projects`, `spec`.
_Avoid_: 内容类型, content type, model

**Post**:
A long-form entry in the `posts` collection. Its URL is its file path relative to the collection, minus the extension. The `slug` front matter field is written by Firefly's own `new-post` script and present in its demo content, but has **no** effect on routing — verified against a real build, and renaming the file therefore changes the URL permanently.
_Avoid_: 文章, article

**Page bundle**:
A post stored as `<slug>/index.md` with its images in the same folder. Every post in a blog repo is one, because the CMS collection only lists bundle-shaped entries; a flat `.md` file is invisible to it.
_Avoid_: 文章目录, folder post

**Dynamic**:
A short-form entry in the `dynamic` collection — one file per entry.
_Avoid_: 说说, moment, status

**Series**:
A named grouping of posts, declared per-post via `series` and `seriesOrder`. The name must match exactly across members.
_Avoid_: 合集, collection (collides with Collection)

**Draft**:
A post carrying `draft: true`. Hidden from readers, still present in the repository. Distinct from an *unpublished* entry, which is a pull request that has not been merged.
_Avoid_: 未发布, unpublished, pending

**Publish**:
Pushing to a blog repo's `master`, which triggers a build. Independent of `draft`.
_Avoid_: 上线, release, deploy

**Schema drift**:
The CMS configuration and `src/content.config.ts` disagreeing. Silent in the editor — a field the schema does not know is dropped without complaint — so it is checked in the deploy workflow instead.
_Avoid_: config error, validation problem

### Deployment

**Release**:
One timestamped directory on the server holding a complete build output.
_Avoid_: 版本, build, artifact

**Current**:
The symlink pointing at the release being served. Rollback means repointing it — no rebuild.
_Avoid_: 线上目录, live

**Deploy**:
Streaming a build output into a release and repointing `current`. Distinct from Publish.
_Avoid_: 上线, publish, release
