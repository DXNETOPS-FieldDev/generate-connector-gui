# Changelog

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
