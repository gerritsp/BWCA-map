# Static server deployment

The release script rebuilds and validates the site, copies only the generated
`maps/` artifact into a versioned release, and atomically switches Caddy's web
root. It never invokes `sudo`, edits Caddy, changes DNS, or deletes old
releases.

Prepare a dedicated virtual environment once, then run the local release check:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-lock.txt
./deploy/release.sh check
```

The check runs `npm ci`, rebuilds the site, runs the Python and JavaScript test
suites, validates all lake bundles, audits production JavaScript dependencies,
rejects generated-site drift, and verifies the CSP hash. It does not access the
server release paths or reload Caddy.

## Server layout

Copy `Caddyfile.example` into the server's Caddy configuration and replace the
example hostname. Keep its web root at `/srv/www/bwca`, or pass the same custom
path to the script. The managed layout is:

```text
/srv/www/bwca             -> /srv/www/bwca-releases/<current-release>
/srv/www/bwca.previous    -> /srv/www/bwca-releases/<previous-release>
/srv/www/bwca-releases/
```

The account running releases must be able to create the two links and write to
the releases directory. It must also be able to use Caddy's local admin API.
Grant those narrow permissions during server setup; do not run the release
script with `sudo`. The script refuses an existing real directory at the web
root, deployment paths inside the Git checkout, symlinks in `maps/`, concurrent
releases, or a dirty checkout.

From a clean, reviewed checkout on the server, activate a release with:

```sh
./deploy/release.sh deploy \
  --web-root /srv/www/bwca \
  --releases-dir /srv/www/bwca-releases \
  --caddyfile /etc/caddy/Caddyfile
```

The script stages the artifact in the releases directory, confirms the copy,
validates the configured web root and CSP, runs `caddy validate`, renames the
release into place, switches the web-root symlink atomically, and only then
reloads Caddy. If reload fails, it restores the former link. Old releases are
left in place intentionally.

Rollback swaps the current and previous releases, so the replaced release can
be restored again if necessary:

```sh
./deploy/release.sh rollback \
  --web-root /srv/www/bwca \
  --releases-dir /srv/www/bwca-releases \
  --caddyfile /etc/caddy/Caddyfile
```

The Content Security Policy contains the SHA-256 hash of the inline script in
`maps/lake_search.html`. If that script changes, update the hash before
deploying; otherwise the browser will correctly refuse to run the changed
inline code. A deploy also verifies that the production Caddyfile permits the
currently live release, preserving a working rollback. Keep both hashes in
`script-src` for one release when they differ. Print the required hash with:

```sh
python deploy/verify_csp.py --print-hashes maps/lake_search.html
```

The example enables HTTPS through Caddy, disables directory browsing, limits
browser capabilities, prevents framing, and restricts scripts and network
requests with a Content Security Policy. The public web root stays separate
from the Git checkout so source files, `.git`, Python scripts, and development
files cannot be served accidentally.

Before announcing the URL, test the root page, lake search, both route
algorithms, fish details, map tiles, and the limitations and legal pages from a
fresh browser profile. Server deployment does not make the underlying public
agency facts secret; copyright protects the project's original code and
presentation as described on `legal.html`.
