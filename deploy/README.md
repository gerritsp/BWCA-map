# Static server deployment

Build and validate the site before publishing it:

```sh
python -m pip install -r requirements-lock.txt
npm ci
npm run vendor
python APP.py
python -m unittest discover -s tests -v
```

Copy the contents of `maps/` to a dedicated web root such as
`/srv/www/bwca`. Copy `Caddyfile.example` into the server's Caddy configuration,
replace the example hostname and root path, validate it with `caddy validate`,
and then reload Caddy.

The Content Security Policy contains the SHA-256 hash of the inline script in
`maps/lake_search.html`. If that script changes, update the hash before
deploying; otherwise the browser will correctly refuse to run the changed
inline code.

The example enables HTTPS through Caddy, disables directory browsing, limits
browser capabilities, prevents framing, and restricts scripts and network
requests with a Content Security Policy. Keep the public web root separate from
the Git checkout so source files, `.git`, Python scripts, and development files
cannot be served accidentally.

Before announcing the URL, test the root page, lake search, both route
algorithms, fish details, map tiles, and the limitations and legal pages from a
fresh browser profile. Server deployment does not make the underlying public
agency facts secret; copyright protects the project's original code and
presentation as described on `legal.html`.
