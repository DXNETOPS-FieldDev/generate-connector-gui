"""Generate Alarm Connector tool — Flask Blueprint."""

import urllib.parse

from werkzeug.exceptions import HTTPException
from flask import Blueprint, current_app, jsonify, render_template, request

from generate_connector import (
    AppNetaAPIError,
    AppNetaAuthError,
    AppNetaNetworkError,
    AppNetaClient,
    build_org_tree,
    build_payload,
    diff_connector,
    merge_with_existing,
    resolve_connector_mode,
    resolve_orgs,
    root_orgs,
    validate_request,
    validate_same_hierarchy,
)
from client import _validate_base_url


def _make_anon_client(base_url: str, api_key: str) -> AppNetaClient:
    """Create a minimal client for org-agnostic read-only calls (no org_id)."""
    client = AppNetaClient.__new__(AppNetaClient)
    client.base_url = base_url.rstrip("/")
    client.api_key  = api_key
    client._cache   = {}
    return client

# Paths the browser is allowed to proxy through /api/lookup.
# Whitelisted to prevent SSRF via arbitrary path injection.
_LOOKUP_ALLOWED = (
    "/v4/organization",
    "/v4/monitoringPoint",
    "/v4/monitoringPolicy",
    "/v4/monitoringPolicyGroup",
    "/v3/tag",
)

connector_bp = Blueprint(
    "connector", __name__, template_folder="templates"
)


def _fmt_error(e: dict | str) -> str:
    if isinstance(e, str):
        return e
    if e.get("type") == "contradiction":
        msg = f"[note] '{e.get('value')}' in both include and exclude — exclude wins, removed from include"
        if e.get("org"):
            msg += f" (org '{e['org']}')"
        if e.get("note"):
            msg += f": {e['note']}"
        return msg
    msg = f"[{e.get('type', '?')}] '{e.get('value')}' not found"
    if e.get("org"):
        msg += f" in org '{e['org']}'"
    if e.get("note"):
        msg += f" ({e['note']})"
    avail = e.get("available", [])
    if avail:
        msg += f". Available: {', '.join(str(a) for a in avail[:10])}"
    return msg


def _coerce_connector_id(data: dict) -> None:
    """Normalize connector.id: empty string → None, numeric string → int."""
    connector = data.get("connector") or {}
    cid = connector.get("id")
    if cid == "" or cid is None:
        connector["id"] = None
    elif isinstance(cid, str):
        connector["id"] = int(cid) if cid.strip().lstrip("-").isdigit() else None
    data["connector"] = connector


MAX_BODY_BYTES = 1024 * 1024

_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'")


class _BadField(ValueError):
    """A request field has the wrong JSON type."""


def _text(data: dict, key: str) -> str:
    """data[key] as a stripped string; missing/null -> ''. Any other type is a 400."""
    val = data.get(key)
    if val is None:
        return ""
    if not isinstance(val, str):
        raise _BadField(f"{key} must be a string.")
    return val.strip()


@connector_bp.errorhandler(_BadField)
def _bad_field(exc):
    return jsonify({"error": str(exc)}), 400


@connector_bp.errorhandler(Exception)  # pyright: ignore[reportArgumentType]  (HTTPException.code is int | None; every real HTTPException has one)
def _unexpected(exc):
    if isinstance(exc, HTTPException):
        return jsonify({"error": exc.description}), exc.code
    current_app.logger.exception("unhandled error in %s", request.path)
    return jsonify({"error": "Internal error."}), 500


@connector_bp.after_request
def _security_headers(resp):
    resp.headers.setdefault("Content-Security-Policy", _CSP)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@connector_bp.before_request
def _guard_post_requests():
    """Block cross-origin and non-JSON POSTs. A hostile page can fire a text/plain POST
    without a CORS preflight; with force-parsed bodies that would drive these endpoints
    (and the key-carrying upstream calls) from the user's browser."""
    if request.method != "POST":
        return None
    origin = request.headers.get("Origin")
    if origin and urllib.parse.urlparse(origin).netloc != request.host:
        return jsonify({"error": "Cross-origin requests are not allowed."}), 403
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json."}), 415
    if (request.content_length or 0) > MAX_BODY_BYTES:
        return jsonify({"error": "Request body too large."}), 413
    return None


def _json_object():
    """The request body as a dict, or None when it is not valid JSON or not an object."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


@connector_bp.get("/connector")
def index():
    return render_template("connector.html")


@connector_bp.post("/api/connector/generate")
def api_connector_generate():
    data = _json_object()
    if data is None:
        return jsonify({"error": "Request body must be a valid JSON object."}), 400

    api_key  = _text(data, "api_key")
    base_url = _text(data, "base_url")
    org_spec = _text(data, "org")

    if not base_url:
        return jsonify({"error": "Base URL is required."}), 400
    try:
        _validate_base_url(base_url)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not api_key:
        return jsonify({"error": "API key is required."}), 400
    if "\r" in api_key or "\n" in api_key:
        return jsonify({"error": "API key must not contain line breaks."}), 400
    for section in ("connector", "webhook", "include", "exclude"):
        if data.get(section) is not None and not isinstance(data[section], dict):
            return jsonify({"error": f"{section} must be an object."}), 400
    cname = (data.get("connector") or {}).get("name")
    if not (isinstance(cname, str) and cname.strip()):
        return jsonify({"error": "Connector name is required."}), 400
    wurl = (data.get("webhook") or {}).get("url")
    if not (isinstance(wurl, str) and wurl.strip()):
        return jsonify({"error": "Webhook URL is required."}), 400

    _coerce_connector_id(data)

    val_errors = validate_request(data)
    if val_errors:
        return jsonify({"errors": val_errors}), 400

    try:
        orgs = AppNetaClient.list_organizations(base_url, api_key)
    except AppNetaNetworkError as exc:
        current_app.logger.warning("generate-connector: network error: %s", exc)
        return jsonify({"error": str(exc)}), 502
    except AppNetaAPIError as exc:
        current_app.logger.warning("generate-connector: API error listing orgs: %s", exc)
        return jsonify({"error": str(exc)}), 400

    roots = root_orgs(orgs)
    if len(roots) > 1:
        return jsonify({
            "error": (
                f"Superadmin API key detected: it spans {len(roots)} unrelated organization "
                f"hierarchies ({len(orgs)} orgs total). Superadmin (account-wide) keys are not "
                "supported; use a key scoped to one organization."
            ),
            "org_tree": build_org_tree(orgs),
            "org_count": len(orgs),
        }), 400

    if org_spec:
        specs = [s.strip() for s in org_spec.split(",") if s.strip()]
        matched, res_errors = resolve_orgs(orgs, specs)
        if res_errors:
            return jsonify({
                "error": "Could not resolve org: " + "; ".join(res_errors),
                "org_tree": build_org_tree(orgs),
                "org_count": len(orgs),
            }), 400
        ok, msg = validate_same_hierarchy(matched, orgs)
        if not ok:
            return jsonify({"error": msg}), 400
        orgs = matched

    all_errors: list[str] = []
    payloads: list[dict] = []
    mode = "CREATE"

    for org in orgs:
        client = AppNetaClient(base_url, api_key, org["id"], org["name"])
        org_errors: list = []
        try:
            payload = build_payload(data, client, org_errors)
            org_mode, connector_id, existing = resolve_connector_mode(client, data)
            mode = org_mode
            diff_lines: list[str] = []
            if org_mode == "PUT":
                payload["id"] = connector_id
                if existing:
                    payload = merge_with_existing(payload, existing, org_errors, org["name"])
                    diff_lines = diff_connector(existing, payload)
                else:
                    org_errors.append(
                        f"Existing connector {connector_id} could not be read in org '{org['name']}' "
                        "(not found, in another org, or the key lacks read access) — "
                        "the PUT payload is NOT merged and may be rejected."
                    )
        except AppNetaNetworkError as exc:
            current_app.logger.warning("generate-connector: network error building payload: %s", exc)
            return jsonify({"error": str(exc)}), 502
        except AppNetaAPIError as exc:
            current_app.logger.warning("generate-connector: API error building payload: %s", exc)
            return jsonify({"error": str(exc)}), 400

        all_errors.extend(_fmt_error(e) for e in org_errors)
        payloads.append({"org_id": org["id"], "org_name": org["name"], "payload": payload, "diff": diff_lines})

    return jsonify({"payloads": payloads, "mode": mode, "errors": all_errors})


@connector_bp.post("/api/lookup")
def api_lookup():
    """Proxy a read-only AppNeta API call for the browser.

    The browser cannot call AppNeta directly due to CORS.  This endpoint
    forwards a whitelisted GET request to the AppNeta API and returns the
    raw JSON response.  The path whitelist prevents SSRF via arbitrary paths.
    """
    data = _json_object()
    if data is None:
        return jsonify({"error": "Request body must be a valid JSON object."}), 400
    base_url = _text(data, "base_url")
    api_key  = _text(data, "api_key")
    path     = _text(data, "path")

    if not base_url or not api_key or not path:
        return jsonify({"error": "base_url, api_key, and path are required."}), 400
    if "\r" in api_key or "\n" in api_key:
        return jsonify({"error": "API key must not contain line breaks."}), 400

    path_base = path.split("?")[0]
    if path_base not in _LOOKUP_ALLOWED:
        return jsonify({"error": "Unsupported lookup path."}), 400

    try:
        _validate_base_url(base_url)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        client = _make_anon_client(base_url, api_key)
        result = client._get(path)
        return jsonify(result)
    except AppNetaNetworkError as exc:
        current_app.logger.warning("lookup: network error: %s", exc)
        return jsonify({"error": str(exc)}), 502
    except AppNetaAPIError as exc:
        current_app.logger.warning("lookup: API error: %s", exc)
        return jsonify({"error": str(exc)}), 400


@connector_bp.post("/api/get/connector/detail")
def api_get_connector_detail():
    """Return full JSON for a single alarm connector by org and connector ID."""
    data         = _json_object()
    if data is None:
        return jsonify({"error": "Request body must be a valid JSON object."}), 400
    base_url     = _text(data, "base_url")
    api_key      = _text(data, "api_key")
    org_id       = data.get("org_id")
    connector_id = data.get("connector_id")

    if not base_url or not api_key or org_id is None or connector_id is None:
        return jsonify({"error": "base_url, api_key, org_id, and connector_id are required."}), 400
    if "\r" in api_key or "\n" in api_key:
        return jsonify({"error": "API key must not contain line breaks."}), 400
    try:
        _validate_base_url(base_url)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        cid = int(connector_id)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return jsonify({"error": "connector_id must be an integer."}), 400
    try:
        oid = int(org_id)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return jsonify({"error": "org_id must be an integer."}), 400

    try:
        client = _make_anon_client(base_url, api_key)
        raw   = client._get(f"/v4/connector/alarm?orgId={oid}")
        items = raw if isinstance(raw, list) else (raw or {}).get("content") or []
        found = next((c for c in items if c.get("id") == cid), None)
        if not found:
            return jsonify({"error": f"Connector {cid} not found in org {oid}."}), 404
        return jsonify({"connector": found})
    except AppNetaAuthError as exc:
        current_app.logger.warning("get_connector_detail: auth error: %s", exc)
        return jsonify({"error": str(exc)}), 403
    except AppNetaNetworkError as exc:
        current_app.logger.warning("get_connector_detail: network error: %s", exc)
        return jsonify({"error": str(exc)}), 502
    except AppNetaAPIError as exc:
        current_app.logger.warning("get_connector_detail: API error: %s", exc)
        return jsonify({"error": str(exc)}), 400


@connector_bp.post("/api/get/connector")
def api_get_connector():
    """Return existing alarm connectors for an org so the UI can offer a picker.

    Auth failures (401/403) are surfaced as distinct, user-readable errors.
"""
    data = _json_object()
    if data is None:
        return jsonify({"error": "Request body must be a valid JSON object."}), 400
    base_url = _text(data, "base_url")
    api_key  = _text(data, "api_key")
    org_id   = data.get("org_id")

    if not base_url or not api_key or org_id is None:
        return jsonify({"error": "base_url, api_key, and org_id are required."}), 400
    if "\r" in api_key or "\n" in api_key:
        return jsonify({"error": "API key must not contain line breaks."}), 400

    try:
        _validate_base_url(base_url)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        oid = int(org_id)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return jsonify({"error": "org_id must be an integer."}), 400

    try:
        client = _make_anon_client(base_url, api_key)
        raw = client._get(f"/v4/connector/alarm?orgId={oid}")
        items = raw if isinstance(raw, list) else (raw or {}).get("content") or []
        connectors = [{"id": c["id"], "name": c.get("name", "(unnamed)")} for c in items if "id" in c]
        return jsonify({"connectors": connectors})
    except AppNetaAuthError as exc:
        current_app.logger.warning("get_connector: auth error for org %s: %s", oid, exc)
        return jsonify({"error": str(exc)}), 403
    except AppNetaNetworkError as exc:
        current_app.logger.warning("get_connector: network error: %s", exc)
        return jsonify({"error": str(exc)}), 502
    except AppNetaAPIError as exc:
        current_app.logger.warning("get_connector: API error: %s", exc)
        return jsonify({"error": str(exc)}), 400
