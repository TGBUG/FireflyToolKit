# Deploy by pushing build output over SSH, not by polling a site-artifacts branch

The original design pushed `dist/` to a `site-artifacts` branch and had the VPS poll it every five minutes. That pairing produced the design's own listed complaints — five-minute publish latency and a branch whose force-pushed history bloats the repository. Building on the runner and streaming `dist/` straight into a timestamped release directory on the VPS removes both, and preserves the rollback story unchanged: repointing the `current` symlink.

The upload is a streamed `tar`, not `rsync`. An earlier draft of this decision assumed rsync, and the assumption failed on the first real deploy: the server had no rsync installed, which is ordinary for a machine a hosting panel manages. Nothing is lost by dropping it — every release lands in a fresh, empty directory, so rsync's delta transfer and `--delete` had nothing to do. The remote needs bash, coreutils and `tar`, all of which Debian ships by default.

`pnpm run build` is an eight-step chain (GitHub card data, LQIPs, VNDB covers, `astro build`, pio pruning, font subsetting, inline-script minification, Pagefind), not a bare `astro build`. The network-touching steps are conditional on feature use — the GitHub card generator only queries repositories that actually appear in content as `::github{repo=...}`, and the VNDB generator is gated on VNDB being configured — so an ordinary blog's build stays offline. Astro's output is plain static by default; the Cloudflare adapter only engages when `CF_WORKERS` is set, so `dist/` is exactly what gets uploaded.

The deploy SSH key belongs to a dedicated non-root user whose write access is limited to the release directory and the `current` symlink. This matters more than usual here: the PAT driving the CMS carries `Contents: write`, which already permits pushing a workflow that reads repository secrets, so the SSH user boundary is the containment that actually holds.

One consequence to preserve deliberately. The origin must not sit behind a Cloudflare proxy: the VPS is a CN2 Hong Kong host chosen for mainland China latency, and Cloudflare's free tier routes through Europe and North America, discarding that advantage entirely. DNS resolves directly to the origin.

Note that `trailingSlash` is `"always"` in Firefly's Astro config, so every URL ends in `/`. A catch-all `try_files ... /index.html` fallback would serve the home page for every missing path instead of a 404.
