# The web server and TLS layer belong to the hosting panel, not to FireflyToolKit

The target server runs Debian 12 with a hosting panel installed that owns nginx: it writes vhost configs under `/www/server/panel/vhost/nginx/`, keeps site roots under `/www/wwwroot/`, and rewrites a site's config whenever the operator changes SSL, the document root, or cross-site protections from its UI. It also ships its own Let's Encrypt issuance and renewal.

So FireflyToolKit does not install nginx configuration and does not run Certbot. `ftk.sh` creates the release directory, creates the `current` symlink, installs the deploy script, and stops there. The site is created once by hand in the panel UI with its document root pointed at `current`.

Writing panel-format vhost files directly was rejected because panel operations overwrite them — which would turn a routine SSL renewal from the UI into a silent outage. Running a second nginx was rejected because the panel's nginx is the same process.

The costs accepted: one manual step during onboarding, TLS renewal living outside this project's control, and a dependency on the panel tolerating a symlink as a document root.

That last dependency was verified by hand on the target server — the panel accepts a symlink as a document root — so the release-directory plus `current`-symlink layout survives. If a future panel update removes that tolerance, the fallback is to copy into a fixed document root instead, which costs the atomic switch and the instant rollback.
