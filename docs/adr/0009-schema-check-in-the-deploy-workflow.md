# The schema check lives in the deploy workflow, and fails the build

`.github/scripts/check-schema.mjs` compares `public/admin/config.json` against the theme's Zod schema in `src/content.config.ts`, and runs in the deploy workflow before the build. Two failure modes motivate it, and only one of them is visible anywhere else:

- A field the CMS declares that the schema does not know is **stripped by Zod without complaint**. The editor reports a successful save and the value goes nowhere. Nothing else in the system notices — not the build, not the preview, not the deploy.
- A field the schema requires that the CMS does not declare cannot be filled in at all, so the build fails, but only after an entry has been published.

**It fails the build rather than warning.** A warning annotation would scroll past, and the first failure mode is silent data loss: publishing with it in place means posts ship with values quietly missing. Failing stops that, and the message names the fields so the fix is mechanical. The cost is that a theme update can block unrelated publishing until someone reconciles the two — accepted, because the alternative is losing data without noticing.

**It lives in the blog repo, not in the tool.** The tool runs once and is gone (ADR-0002). The schema changes whenever the theme is updated, which is months later, so the check has to live where that happens: a workflow that runs on every publish.

**The CMS configuration is JSON, not YAML, so that this check needs no YAML parser.** Sveltia loads `config.json` given a `<link rel="cms-config-url">` in `public/admin/index.html`, and its own documentation notes JSON "is mainly intended for programmatic generation of configuration files" — which is what this is. The cost is that the configuration can no longer carry comments; the reasoning they used to hold lives in `FIREFLYTOOLKIT.md` and the ADRs instead.

**The schema is read by scanning the TypeScript rather than importing it**, because `src/content.config.ts` imports from `astro:content`, which only resolves inside Astro. So the check is a small scanner — strip comments, brace-match each `defineCollection`, split each `z.object` body on top-level commas — with no dependencies at all. The risk is a scanner bug producing a false failure; it was verified against the real theme (0 findings on a matching config) and against a deliberately broken one (2 errors, exit 1), and the theme changes rarely enough for a scanner to be the better trade than a build-time dependency.

Fields are deliberately allowed to sit outside the schema: `body` is content rather than front matter, `slug` is written by the theme's own `new-post` script and ignored by its routing, and `_slug` is the tool's own field consumed by the `path` template.
