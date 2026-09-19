# Fireflyer

Tooling that turns a stock Firefly Astro blog into a self-hosted, browser-editable publishing system. It owns the configuration injected into a blog repository, plus the automation that builds and deploys it.

## Language

### Repositories

**Firefly**:
The upstream Astro blog theme at `CuteLeaf/Firefly` (public). Consumed and merged from, never modified.
_Avoid_: 主题仓库, theme repo

**Fireflyer**:
This repository. The single source of truth for everything injected into a blog repo; holds no CMS, blog, or server code of its own.
_Avoid_: 系统, 平台, backend, 服务端, 编写端

**Blog repo**:
A private repository holding one blog instance — Firefly's source, that blog's content, and the injected additive layer. Produced by mirroring, not forking.
_Avoid_: 博客原仓库, 内容仓库, fork

**Upstream**:
Firefly as reached from a blog repo, via a git remote named `upstream`. The channel through which theme updates arrive.

**Additive layer**:
The files Fireflyer injects into a blog repo. Every filename in it is one Firefly does not ship — no file Firefly ships is ever modified.
_Avoid_: 附加层, overlay, patch

**Inject**:
Writing the additive layer into a blog repo, idempotently.
_Avoid_: 部署, install, sync

### Content

**Collection**:
One of Firefly's four content types, declared in `src/content.config.ts`: `posts`, `dynamic`, `projects`, `spec`.
_Avoid_: 内容类型, content type, model

**Post**:
A long-form entry in the `posts` collection. Its URL is its file path relative to the collection, minus the extension. The `slug` frontmatter field is written by Firefly's own `new-post` script and present in its demo content, but does **not** affect routing — verified against a real build (a post at `guide/index.md` declaring `slug: hello-world` renders to `posts/guide/`, with no `hello-world` anywhere in `dist/`). Renaming the file therefore changes the URL permanently.
_Avoid_: 文章, article

**Page bundle**:
A post stored as `<slug>/index.md` with its images in the same folder. Every post in a blog repo is one, because the CMS's collection only lists bundle-shaped entries; a flat `.md` file is invisible to it.
_Avoid_: 文章目录, folder post

**Dynamic**:
A short-form entry in the `dynamic` collection — one file per entry.
_Avoid_: 说说, moment, status

**Series**:
A named grouping of posts, declared per-post via `series` and `seriesOrder`. The name must match exactly across members.
_Avoid_: 合集, collection (collides with Collection)

**Draft**:
A post carrying `draft: true`. Hidden from readers, still present in the repository.
_Avoid_: 未发布, unpublished, pending

**Publish**:
Pushing to a blog repo's `master`, which triggers a build. Independent of `draft`.
_Avoid_: 上线, release, deploy

### Deployment

**Release**:
One timestamped directory on the VPS holding a complete build output.
_Avoid_: 版本, build, artifact

**Current**:
The symlink pointing at the release being served. Rollback means repointing it — no rebuild.
_Avoid_: 线上目录, live

**Deploy**:
Placing a build output into a release and repointing `current`. Distinct from Publish.
_Avoid_: 上线, publish, release
