# Fireflyer

Turns a stock [Firefly](https://github.com/CuteLeaf/Firefly) Astro blog into a self-hosted, browser-editable site, and keeps it that way across theme updates.

Fireflyer is a scaffold plus automation, not an application. It holds the configuration that gets copied into a blog repository, and the four commands that put it there. It does not serve any traffic and has no runtime of its own.

中文说明见 [README.md](README.md).

## The two repositories

| | |
| --- | --- |
| **This one** (public) | The single source of truth for everything injected. Holds no blog content. |
| **Your blog repo** (private) | Firefly's source, your content, and the injected files. |

The blog repository is created by **mirroring** Firefly rather than forking it, because GitHub refuses to make a fork of a public repository private and Firefly is public. Full history is required either way: merging theme updates later needs a shared ancestor.

Theme updates arrive through an `upstream` remote and merge normally, which is Firefly's own recommended approach. Every file Fireflyer adds is one the theme does not ship, so those merges are conflict-free.

## Install

Requires Python 3.13 or newer. The blog itself needs Node 22 and pnpm; Fireflyer does not.

```bash
uv tool install git+https://github.com/TGBUG/Fireflyer
```

## Setup

### 1. Create an **empty** private repository, by hand

This is the only manual step of onboarding. Automating it needs `Administration: write`, which is not a permission worth keeping resident on an operator's machine. The repository has to be empty: `init` refuses one that already has branches, so that it cannot clobber existing work.

### 2. One command does the rest

```bash
export GH_TOKEN=...            # needs Contents: write and Actions: write
fireflyer init <owner>/<repo>
```

`GH_TOKEN` has to be able to **reach that repository**. Fine-grained tokens authorise repositories one by one, so **deleting and recreating a repository leaves the token's grants stale even when the name is identical** — the new repository has a new identity. The symptom is a 404 on everything to do with it, because fine-grained tokens deliberately do not distinguish "does not exist" from "not permitted". Add the new repository to the token's access list.

It then:

1. **Mirrors** Firefly's full history. It pushes `master` **on its own first**, then the remaining branches and tags — the first ref pushed into an empty repository becomes its default branch, and pushing everything at once lets GitHub pick, which it does not do in favour of `master`.
2. Clones a working tree locally, and points `upstream` at Firefly.
3. Writes the injected files, commits, and pushes.
4. **Disables the theme's own `build.yml` and `deploy.yml`**, which trigger on every push and cost far more runner time than the deploy.

Step 4 has to come after the push: GitHub registers a repository's workflows when work first arrives on a branch, so immediately after mirroring the list is empty and there is nothing to disable.

Pass `--dir` to choose where the working tree goes; it defaults to `./<repository name>`.

### 3. Prepare the server

```bash
fireflyer bootstrap-vps <user>@<host> --base /home/deploy/fireflyer
```

This creates the release directory, gives the `current` symlink something valid to point at, and installs the release script.

It deliberately does not touch nginx, TLS, or user accounts — your hosting panel owns those, and anything Fireflyer wrote there would be overwritten the next time you changed a setting in the panel. See `docs/adr/0006`.

`--base` must be a POSIX path, because it is used on the server. From Git Bash on Windows, MSYS rewrites arguments that look like POSIX paths; prefix the command with `MSYS_NO_PATHCONV=1` to stop it.

### 4. By hand

- Create a non-root deploy user, and put its public key in `authorized_keys`. It needs write access to `--base` and nothing else.
- In your hosting panel, create the site for your domain with its document root set to `<base>/current`, and issue TLS from the panel.
- In the blog repository, add repository secrets `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` and `VPS_BASE`.
- Delete Firefly's demo content from `src/content/posts/` and `src/content/dynamic/`, and set `siteConfig.site_url` in `src/config/siteConfig.ts`.

### 5. Write

Open `https://<your-domain>/admin/` and sign in with a GitHub **fine-grained** personal access token. It needs three repository permissions:

| Permission | Why |
| --- | --- |
| `Contents: read and write` | read and write posts and their media |
| `Pull requests: read and write` | open, merge and delete the workflow branches' pull requests |
| `Issues: read and write` | change an entry's status — Sveltia does this by patching the issue behind the pull request |

With all three, writing, saving drafts, moving an entry through its statuses, and publishing **all happen inside the CMS**. Nothing sends you to the GitHub website.

Omitting `Issues` produces a misleading symptom: drafts save and open pull requests correctly, but any status change reports "cannot change status". Saving only needs `POST /issues/{n}/labels`, while changing the status needs `PATCH /issues/{n}`.

## Commands

| Command | What it does |
| --- | --- |
| `fireflyer init <owner/name>` | Takes an empty repository all the way to writable: mirror, inject, push, disable the theme's CI. |
| `fireflyer inject <repo>` | Writes the layer. Idempotent; `--check` reports drift and exits non-zero without writing. Re-run after every fresh clone. |
| `fireflyer drift-check <repo>` | Compares the CMS config against the theme's Zod schema, and checks repository state. |
| `fireflyer bootstrap-vps <user@host> --base <dir>` | Prepares the server to receive deploys. `--print-only` prints the remote script instead of running it. |

## Why `inject` has to be re-run

`src/content/.gitattributes` marks your content `merge=ours`, but that name is defined in `.git/config`, which git never commits. A fresh clone therefore has the attribute and no working driver. `fireflyer inject .` re-establishes it; `drift-check` warns when it is missing.

Note also that a merge driver only handles files present on both sides. When a theme update edits a demo post you deleted, git raises a `modify/delete` conflict and ignores the driver entirely, leaving upstream's copy behind. `scripts/fireflyer-merge-upstream.sh` — injected into the blog repository — resolves that case and reports content upstream has added.

## What the blog repository's own documentation covers

The writing workflow, the limitations a writer will run into, and how to deploy and roll back are documented in the blog repository itself, in `FIREFLYER.md`. That file is injected too, so edit it here.

## Design

The reasoning behind each decision is recorded in `docs/adr/`. `CONTEXT.md` is the glossary — note that it separates *publish* (a push to `master`) from *deploy* (placing a build output and repointing `current`), which earlier drafts of this project conflated.
