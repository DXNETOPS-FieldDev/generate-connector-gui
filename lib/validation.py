"""Input validation for connector request payloads."""

import re

from constants import VALID_SEVERITIES, VALID_NOISE_FILTERS, VALID_NOTIFY_ON, VALID_METHODS, VALID_AUTH_TYPES


def _has_ctrl(s: str) -> bool:
    """True if s contains null bytes or ASCII control chars other than tab/newline/CR."""
    return any((ord(c) < 0x20 and c not in "\t\n\r") or ord(c) == 0x7F for c in s)


def _has_crlf(s: str) -> bool:
    """True if s contains CR or LF — blocks HTTP header injection."""
    return "\r" in s or "\n" in s


# RFC 7230 token: the only characters allowed in an HTTP header field name.
_HEADER_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


def validate_request(data: dict) -> list[str]:
    """Validate connector payload data. Returns human-readable error strings.

    Checks enum values, required fields, string safety (no control characters),
    URL format, and header name validity. Does not make any API calls.
    Returns an empty list when the data is valid.
    """
    errors: list[str] = []

    connector = data.get("connector") or {}
    raw_name = connector.get("name") or ""
    if not isinstance(raw_name, str):
        errors.append("connector.name: must be a string")
    elif not raw_name.strip():
        errors.append("connector.name: required")
    elif len(raw_name.strip()) > 255:
        errors.append("connector.name: too long (max 255 characters)")
    elif _has_ctrl(raw_name) or _has_crlf(raw_name):
        errors.append("connector.name: contains invalid control characters")

    cid = connector.get("id")
    if cid is not None and cid != "" and (isinstance(cid, bool) or not isinstance(cid, (int, str))
                                           or (isinstance(cid, int) and cid <= 0)):
        errors.append(f"connector.id: must be a positive integer, got {cid!r}")

    desc = connector.get("description") or ""
    if not isinstance(desc, str):
        errors.append("connector.description: must be a string")
    elif desc:
        if len(desc) > 2000:
            errors.append("connector.description: too long (max 2000 characters)")
        elif _has_ctrl(desc):
            errors.append("connector.description: contains invalid control characters")

    notify_on = data.get("notify_on")
    if notify_on is None:
        notify_on = []
    elif not isinstance(notify_on, list):
        errors.append("notify_on: must be a list")
        notify_on = []
    elif not notify_on:
        errors.append("notify_on: select at least one event, or omit it for the default (raised and cleared)")
    invalid_notify = [n for n in notify_on if str(n).upper() not in VALID_NOTIFY_ON]
    if invalid_notify:
        errors.append(
            f"notify_on: invalid value(s) {invalid_notify!r}  —  "
            f"valid: {sorted(VALID_NOTIFY_ON)}"
        )

    for block in ("include", "exclude"):
        section = data.get(block) or {}

        sev = section.get("severity") or []
        invalid_sev = [s for s in sev if str(s).upper() not in VALID_SEVERITIES]
        if invalid_sev:
            errors.append(
                f"{block}.severity: invalid value(s) {invalid_sev!r}  —  "
                f"valid: {sorted(VALID_SEVERITIES)}"
            )

        nf = section.get("noise_filter") or []
        invalid_nf = [n for n in nf if str(n).upper() not in VALID_NOISE_FILTERS]
        if invalid_nf:
            errors.append(
                f"{block}.noise_filter: invalid value(s) {invalid_nf!r}  —  "
                f"valid: {sorted(VALID_NOISE_FILTERS)}"
            )

        for i, v in enumerate(section.get("alarm_rule_ids") or []):
            try:
                if int(v) <= 0:
                    errors.append(f"{block}.alarm_rule_ids[{i}]: must be a positive integer, got {v!r}")
            except (TypeError, ValueError):
                errors.append(f"{block}.alarm_rule_ids[{i}]: must be an integer, got {v!r}")

        # Dedicated numeric-only ID fields -- direct passthrough into
        # monitoringPointId/monitoringPolicyId/monitoringPolicyGroupId, no API
        # lookup. Avoid mixing an ID and a name for the same resource in one
        # filter block.
        for id_field in ("monitoring_point_ids", "monitoring_policy_ids", "monitoring_policy_group_ids"):
            raw = section.get(id_field)
            if raw is None:
                continue
            values = [raw] if isinstance(raw, int) else raw
            if not isinstance(values, list):
                errors.append(f"{block}.{id_field}: must be an integer or a list of integers")
                continue
            for i, v in enumerate(values):
                try:
                    if isinstance(v, bool) or int(v) <= 0:
                        errors.append(f"{block}.{id_field}[{i}]: must be a positive integer, got {v!r}")
                except (TypeError, ValueError):
                    errors.append(f"{block}.{id_field}[{i}]: must be an integer, got {v!r}")

        for field in (
            "monitoring_point_names", "monitoring_point_types",
            "monitoring_policy_names", "monitoring_policy_group_names",
            "tags", "targets",
        ):
            vals = section.get(field) or []
            if not isinstance(vals, list):
                errors.append(f"{block}.{field}: must be a list")
                continue
            for i, item in enumerate(vals):
                if not isinstance(item, str):
                    errors.append(f"{block}.{field}[{i}]: must be a string, got {type(item).__name__}")
                elif _has_ctrl(item):
                    errors.append(f"{block}.{field}[{i}]: contains invalid control characters")

    webhook = data.get("webhook") or {}
    wh_url = webhook.get("url") or ""
    if not isinstance(wh_url, str):
        errors.append("webhook.url: must be a string")
    elif not wh_url.strip():
        errors.append("webhook.url: required")
    elif not wh_url.strip().startswith(("http://", "https://")):
        errors.append("webhook.url: must start with http:// or https://")
    elif _has_crlf(wh_url) or _has_ctrl(wh_url):
        errors.append("webhook.url: contains invalid control characters")

    method = webhook.get("method") or "POST"
    method = method.upper() if isinstance(method, str) else str(method)
    if method not in VALID_METHODS:
        errors.append(
            f"webhook.method: invalid value {method!r}  —  "
            f"valid: {sorted(VALID_METHODS)}"
        )

    auth = webhook.get("auth") or {}
    auth_type = auth.get("type") or "NONE"
    auth_type = auth_type.upper() if isinstance(auth_type, str) else str(auth_type)
    if auth_type not in VALID_AUTH_TYPES:
        errors.append(
            f"webhook.auth.type: invalid value {auth_type!r}  —  "
            f"valid: {sorted(VALID_AUTH_TYPES)}"
        )
    else:
        if auth_type == "BASIC":
            username = auth.get("username") or ""
            password = auth.get("password") or ""
            for field, val in (("username", username), ("password", password)):
                if not isinstance(val, str):
                    errors.append(f"webhook.auth.{field}: must be a string")
            username = username if isinstance(username, str) else ""
            password = password if isinstance(password, str) else ""
            if _has_crlf(username) or _has_ctrl(username):
                errors.append("webhook.auth.username: contains invalid control characters")
            if _has_crlf(password) or _has_ctrl(password):
                errors.append("webhook.auth.password: contains invalid control characters")
        elif auth_type == "BEARER":
            token = auth.get("token") or ""
            if not isinstance(token, str):
                errors.append("webhook.auth.token: must be a string")
                token = ""
            if _has_crlf(token) or _has_ctrl(token):
                errors.append(
                    "webhook.auth.token: contains invalid control characters — "
                    "CRLF in a Bearer token would inject headers into AppNeta's webhook calls"
                )

    headers = webhook.get("headers") or []
    if not isinstance(headers, list):
        errors.append("webhook.headers: must be a list")
    else:
        for i, h in enumerate(headers):
            if not isinstance(h, dict):
                errors.append(
                    f"webhook.headers[{i}]: must be an object with 'key' and 'value' fields"
                )
                continue
            hkey = h.get("key") or ""
            if not isinstance(hkey, str):
                errors.append(f"webhook.headers[{i}].key: must be a string")
            elif not hkey.strip():
                errors.append(f"webhook.headers[{i}].key: required")
            elif not _HEADER_TOKEN.match(hkey.strip()):
                errors.append(
                    f"webhook.headers[{i}].key: invalid header name {hkey!r}  —  "
                    "letters, digits and !#$%&'*+-.^_`|~ only"
                )
            hval = h.get("value")
            if not isinstance(hval, str):
                errors.append(f"webhook.headers[{i}].value: required, and must be a string")
            elif _has_crlf(hval) or _has_ctrl(hval):
                errors.append(
                    f"webhook.headers[{i}].value: contains invalid control characters — "
                    "CRLF in a header value would split the HTTP response AppNeta sends to your webhook"
                )

    return errors
