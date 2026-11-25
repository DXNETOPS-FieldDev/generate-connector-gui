# Changelog

## v0.2.0

New home for releases.

- Releases are now published at https://github.com/DXNETOPS-FieldDev/generate-connector-gui. The earlier
  v0.1.0, v0.1.1 and v0.1.2 tags are unchanged.
- No change in behavior. Internal code-quality cleanups only.

## v0.1.2

Consistent API key scope checks.

- An API key that spans several unrelated organization hierarchies is now rejected even when you
  enter an organization in the Org field, matching the command-line tool. Use a key scoped to one
  hierarchy.
- Documentation and help text describing key scope were simplified.

## v0.1.1

Security hardening and UPDATE-mode fixes.

- The server no longer follows redirects, and `base_url` must be a plain `https://host[:port]`
  (no credentials, query or fragment), so the API key is only ever sent to the host you entered.
- API endpoints accept same-origin `application/json` requests only, limit request size, and send
  `Content-Security-Policy`, `X-Content-Type-Options` and `Cache-Control: no-store` headers.
- UPDATE mode now removes authentication and headers you cleared, can turn TLS verification back on,
  resolves include/exclude conflicts created by the merge, and shows a diff of what is actually sent.
  A warning appears when the existing connector cannot be read.
- Stricter input validation: header names follow RFC 7230, CRLF is rejected in raw values, and
  malformed JSON types return a clear error instead of a server error.
- Numeric monitoring point entries are checked against your organization's monitoring points.
- The documented `docker run` and `docker-compose.yml` publish the port on `127.0.0.1` only.

## v0.1.0

Initial release.

- Browser-based generator for AppNeta alarm connector JSON, packaged as a Docker image; `docker run`
  is the whole installation.
- Enter an AppNeta API key, choose organizations, configure include and exclude filters (severity,
  monitoring point type, tags, names, policies, policy groups) and download POST-ready JSON.
- CREATE and UPDATE modes; UPDATE merges your changes onto the existing connector.
- The API key is held in your browser session and is never written to disk or logged; the container
  runs as an unprivileged user and includes a health check.
- Unit tests in `test/`.
