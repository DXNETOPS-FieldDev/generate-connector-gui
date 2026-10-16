"""Input validation for connector request payloads."""

from constants import VALID_SEVERITIES, VALID_NOISE_FILTERS, VALID_NOTIFY_ON, VALID_METHODS, VALID_AUTH_TYPES


def _has_ctrl(s: str) -> bool:
    """True if s contains null bytes or ASCII control chars other than tab/newline/CR."""
    return any(ord(c) < 0x20 and c not in "\t\n\r" for c in s)


def _has_crlf(s: str) -> bool:
    """True if s contains CR or LF — blocks HTTP header injection."""
    return "\r" in s or "\n" in s


def validate_request(data: dict) -> list[str]:
    """Validate connector payload data. Returns human-readable error strings.

    Checks enum values, required fields, string safety (no control characters),
    URL format, and header name validity. Does not make any API calls.
    Returns an empty list when the data is valid.
    """
    errors: list[str] = []

    connector = data.get("connector") or {}
    name = (connector.get("name") or "").strip()
    if not name:
        errors.append("connector.name: required")
    elif len(name) > 255:
        errors.append("connector.name: too long (max 255 characters)")
    elif _has_ctrl(name) or _has_crlf(name):
        errors.append("connector.name: contains invalid control characters")

    desc = connector.get("description") or ""
    if desc:
        if len(desc) > 2000:
            errors.append("connector.description: too long (max 2000 characters)")
        elif _has_ctrl(desc):
            errors.append("connector.description: contains invalid control characters")

    notify_on = data.get("notify_on") or []
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
    wh_url = (webhook.get("url") or "").strip()
    if not wh_url:
        errors.append("webhook.url: required")
    elif not wh_url.startswith(("http://", "https://")):
        errors.append("webhook.url: must start with http:// or https://")
    elif _has_crlf(wh_url) or _has_ctrl(wh_url):
        errors.append("webhook.url: contains invalid control characters")

    method = (webhook.get("method") or "POST").upper()
    if method not in VALID_METHODS:
        errors.append(
            f"webhook.method: invalid value {method!r}  —  "
            f"valid: {sorted(VALID_METHODS)}"
        )

    auth = webhook.get("auth") or {}
    auth_type = (auth.get("type") or "NONE").upper()
    if auth_type not in VALID_AUTH_TYPES:
        errors.append(
            f"webhook.auth.type: invalid value {auth_type!r}  —  "
            f"valid: {sorted(VALID_AUTH_TYPES)}"
        )
    else:
        if auth_type == "BASIC":
            username = auth.get("username") or ""
            password = auth.get("password") or ""
            if _has_crlf(username) or _has_ctrl(username):
                errors.append("webhook.auth.username: contains invalid control characters")
            if _has_crlf(password) or _has_ctrl(password):
                errors.append("webhook.auth.password: contains invalid control characters")
        elif auth_type == "BEARER":
            token = auth.get("token") or ""
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
            hkey = (h.get("key") or "").strip()
            if not hkey:
                errors.append(f"webhook.headers[{i}].key: required")
            elif any(c in hkey for c in " \t:\r\n") or _has_ctrl(hkey):
                errors.append(
                    f"webhook.headers[{i}].key: invalid header name {hkey!r}  —  "
                    "no whitespace, colons, or control characters"
                )
            hval = h.get("value") or ""
            if _has_crlf(hval) or _has_ctrl(hval):
                errors.append(
                    f"webhook.headers[{i}].value: contains invalid control characters — "
                    "CRLF in a header value would split the HTTP response AppNeta sends to your webhook"
                )

    return errors
