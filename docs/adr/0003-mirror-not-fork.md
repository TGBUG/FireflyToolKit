# Blog repos are mirrored from Firefly, not forked

GitHub refuses to make a fork of a public repository private, and Firefly is public — so a private blog repo cannot be a fork. Each blog repo is created empty and populated with `git clone --bare` followed by `git push --mirror`, which preserves full history.

Full history is mandatory rather than cosmetic: without a shared ancestor, every later `git merge upstream/master` fails with unrelated histories. The fork *relationship* is not needed — Firefly's own update guide only requires an `upstream` remote, and merging works without it. The "Leave fork network" setting is the alternative route to a private repo, but it is a manual per-repo step that leaves a repo whose history is tied to a network it no longer belongs to; mirroring is one fewer thing to get wrong.

One detail of the mirroring is load-bearing. Pushing every branch at once (`git push --mirror`) leaves GitHub to pick the default branch out of the fourteen it receives — measured, it picked `TailwindCSS-v4`, not `master`. The first ref pushed into an empty repository becomes the default, and an account's default-branch preference does not apply to a repository you push into yourself, so `master` has to be pushed first, on its own. `init` does exactly that. The alternative — correcting the default branch through the API afterwards — needs the same `Administration: write` this ADR already declines to hold.

Everything after repository creation is automated, because it needs only `Contents: write` and `Actions: write`: the mirror itself, the working clone, the `upstream` remote, the injection, and disabling the theme's CI. Disabling has to follow the first push, because that push is what makes GitHub register the workflows at all.

Creating the private repo stays a manual step. Automating it would require an `Administration: write` PAT held on the operator's machine, which is a larger standing exposure than the one-time convenience is worth.
