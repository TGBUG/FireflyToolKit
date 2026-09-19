# Drafts live on `master`, guarded by a pre-build check

**Status: superseded by [ADR-0008](0008-drafts-live-on-workflow-branches.md)**, which records that the Editorial Workflow this ADR treats as unimplemented does in fact exist. The premise below is wrong; the file is kept as the record of what was believed at the time.

Sveltia commits every save to `backend.branch`, including posts marked `draft: true`. Its Editorial Workflow — which would isolate each draft on its own branch behind a review step — is described in Sveltia's own docs but not implemented: a third-party check dated 2026-07-20 confirmed that adding Decap's `publish_mode: editorial_workflow` produces neither branches nor pull requests. The documented workaround is to point `backend.branch` at a `drafts` branch and merge by hand, which permits only one active draft at a time and turns every publish into manual git work — directly opposed to the goal this project exists to serve.

So drafts are committed straight to `master`. The obvious objection is that every save then triggers a full build. At 1–3 minutes per Astro build and roughly ten saves per post, that is 25–45% of a private repository's 2000 monthly Actions minutes. The mitigation is `.github/scripts/should-build.mjs`: the build is skipped when every changed file sits under `src/content/` and every changed post is still a draft. Flipping `draft` to `false`, editing `src/config/`, or touching anything outside `src/content/` all still build.

Two alternatives were rejected. **Branch isolation** is blocked upstream, per above. **Making the blog repo public** would make Actions minutes unlimited and remove the whole problem, but drafts would become world-readable — draft privacy is a requirement, so this is out.

A future maintainer should not "fix" the drafts-on-master arrangement by moving drafts to a branch: Sveltia cannot write to more than one branch today.
