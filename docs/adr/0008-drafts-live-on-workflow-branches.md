# Drafts live on editorial-workflow branches, not on master

Supersedes ADR-0005, which committed drafts straight to `master` behind a pre-build guard. That decision rested on Sveltia's Editorial Workflow being unimplemented — a third-party report dated 2026-07-20 said so, and this project acted on it. It is implemented. Sveltia's own documentation describes `publish_mode: editorial_workflow`: each unpublished entry gets a `cms/[collection]/[slug]` branch opening a draft pull request, statuses move through Draft / In Review / Ready on a board, and publishing merges the pull request.

Because drafts sit on their own branches, saving a draft reaches no branch that builds. ADR-0005's guard existed only to stop draft saves burning Actions minutes; the workflow removes the cost rather than mitigating it, so `should-build.mjs` is dropped entirely.

Two constraints follow.

**The build must never run on `cms/*` branches or on pull requests.** Editorial Workflow deliberately permits a draft to be saved with required fields empty, and Firefly declares `published: z.date()` as required. Sveltia's docs warn that such a draft turns the branch's build red. Relaxing the schema is not available to us — `src/content.config.ts` is a theme core file that ADR-0002 forbids touching — so the deploy workflow triggers on pushes to `master` only.

**The PAT needs three repository permissions.** Verified against a real repository: `Contents: read and write` covers the branch and the commit, `Pull requests: read and write` covers creating, merging and deleting the pull request, and `Issues: read and write` covers the status label. With all three the entire workflow — writing, saving drafts, moving an entry between statuses, publishing — happens inside the CMS.

`Issues` is the one that is easy to miss, and it fails in a misleading way. Saving a draft only calls `POST /issues/{n}/labels`, so it succeeds without the permission, producing a branch, a draft pull request and the `sveltia-cms/draft` label. Changing the status calls `PATCH /issues/{n}` — Sveltia patches the issue behind the pull request — which does not.

**An earlier version of this section recorded the opposite conclusion, and it was wrong**, so the mistake is written down here to stop it being reached twice. It held that a fine-grained token could not drive the status change at all and that publishing therefore had to be finished on GitHub. That rested on `POST /pulls/{n}/ready_for_review` returning 404 — a real behaviour of that endpoint for fine-grained tokens, but beside the point, because Sveltia never calls it: its source notes that "the REST API cannot toggle the draft state" and uses the GraphQL mutation `markPullRequestReadyForReview` instead. A true observation about an endpoint outside the actual path, promoted to a cause it was not.
