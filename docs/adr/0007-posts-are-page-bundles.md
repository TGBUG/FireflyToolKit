# Posts are page bundles, so the collection only sees bundle-shaped entries

Co-locating a post's images beside it requires each entry to own a folder. Sveltia's media documentation is explicit: a relative `media_folder` "only makes each entry's media its own if the entry has a folder of its own to keep it in", and "without either, entries are files sharing one folder, so a relative `media_folder` resolves to the collection folder and the media is shared as well". The `path: '{{slug}}/index'` option is what gives each entry that folder.

The consequence was learned by testing rather than by reading: **a collection whose `path` template is a bundle pattern lists only bundle-shaped entries.** Firefly's demo content is a mix — thirteen flat `.md` files plus one `guide/index.md` — and only the bundle-shaped one appeared in the CMS. This is not a defect to work around; a collection has one shape.

So every post in a blog repo is `<slug>/index.md` with its images in the same folder. The costs, which also belong in the user-facing README:

- Firefly's demo posts are flat, so the CMS cannot see them; they have to be deleted from disk.
- `pnpm new-post foo.md` — Firefly's own script — writes a flat file the CMS will never show. Use `pnpm new-post foo/index.md`, or create posts in the CMS. Upstream expects this form: the script strips a trailing `/index` when deriving the filename.
- `extension: md` is declared, so an `.mdx` post would be invisible even in bundle shape.

Rejected: flat posts with a shared media folder, which is what Firefly's own demo does (`image: ./images/firefly2.avif` from flat files). Simpler, and consistent with upstream tooling, but it gives up per-post media isolation, `astro:assets` optimization, and Sveltia's automatic deletion of an entry's media when that entry is deleted.

Confirmed by test: images uploaded through the CMS — both the cover field and images pasted into the body — land in the entry's own folder. The concern that body images would bypass the per-collection setting and land in a global `public/uploads` proved unfounded.
