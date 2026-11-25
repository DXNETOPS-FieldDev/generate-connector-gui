"""Alarm connector JSON payload builder."""

from typing import TYPE_CHECKING, Any

from resolution import _has_glob, is_numeric, resolve_mp_types, resolve_tags, resolve_to_ids

if TYPE_CHECKING:
    from client import AppNetaClient


def build_filter(section: dict, client: "AppNetaClient", errors: list) -> dict:
    out: dict[str, Any] = {}

    if section.get("severity"):
        out["severity"] = [s.upper() for s in section["severity"]]

    if section.get("noise_filter"):
        out["noiseFilter"] = [n.upper() for n in section["noise_filter"]]

    # Alarm rule IDs must be obtained from the AppNeta GUI — no API endpoint available.
    alarm_rule_ids_raw = section.get("alarm_rule_ids", [])
    if alarm_rule_ids_raw:
        numeric_ids = [int(x) for x in alarm_rule_ids_raw if is_numeric(str(x))]
        if numeric_ids:
            out["alarmRuleId"] = numeric_ids

    if section.get("targets"):
        out["target"] = list(section["targets"])

    policy_names = [str(x) for x in section.get("monitoring_policy_names", [])]
    if policy_names:
        ids = resolve_to_ids(
            policy_names, client.list_monitoring_policies(), "name", "id", "policy", errors, client.org_name
        )
        if ids:
            out["monitoringPolicyId"] = ids

    group_names = [str(x) for x in section.get("monitoring_policy_group_names", [])]
    if group_names:
        numeric_group_ids = [int(x) for x in group_names if is_numeric(x)]
        name_strs = [x for x in group_names if not is_numeric(x)]
        resolved_ids = client.group_ids_for_names(name_strs, errors) if name_strs else []
        group_ids = sorted(set(numeric_group_ids + resolved_ids))
        if group_ids:
            out["monitoringPolicyGroupId"] = group_ids

    mp_names = [str(x) for x in section.get("monitoring_point_names", [])]
    if mp_names:
        name_strs = [x.strip() for x in mp_names]
        glob_names = [n for n in name_strs if _has_glob(n)]
        # Numeric entries go through resolve_to_ids too, so an ID that is not in the
        # live catalog is reported instead of silently sent.
        plain_names = [n for n in name_strs if not _has_glob(n)]
        if glob_names:
            out["monitoringPointName"] = glob_names
        resolved_ids = resolve_to_ids(
            plain_names, client.list_monitoring_points(), "name", "id", "monitoring point", errors, client.org_name
        ) if plain_names else []
        all_mp_ids = sorted(set(resolved_ids))
        if all_mp_ids:
            out["monitoringPointId"] = all_mp_ids

    mp_types = list(section.get("monitoring_point_types", []))
    if mp_types:
        out["monitoringPointType"] = resolve_mp_types(mp_types, client.list_monitoring_points(), errors, client.org_name)

    raw_tags    = section.get("tags", [])
    tag_specs   = [t for t in raw_tags if isinstance(t, str)]
    config_tags = [t for t in raw_tags if isinstance(t, dict)]
    tags = resolve_tags(tag_specs, config_tags, client, errors)
    if tags:
        out["tag"] = tags

    # Dedicated numeric-only ID fields -- direct passthrough, no API lookup.
    # Merged (union) with whatever the *_names fields' numeric passthrough
    # already contributed to the same output key, so using both together is
    # safe. A dedicated field exists so the intent (an ID) is explicit,
    # instead of relying solely on the numeric-string heuristic under *_names.
    _NUMERIC_ID_FIELDS = (
        ("monitoring_point_ids",        "monitoringPointId"),
        ("monitoring_policy_ids",       "monitoringPolicyId"),
        ("monitoring_policy_group_ids", "monitoringPolicyGroupId"),
    )
    for toml_key, out_key in _NUMERIC_ID_FIELDS:
        raw = section.get(toml_key)
        if raw is None:
            continue
        values = [raw] if isinstance(raw, int) else list(raw)
        ids = sorted({int(x) for x in values if isinstance(x, int) and not isinstance(x, bool) and x > 0})
        if ids:
            out[out_key] = sorted(set(out.get(out_key, [])) | set(ids))

    return out


def _remove_contradictions(
    include_block: dict, exclude_block: dict, errors: list, org_name: str
) -> None:
    """Resolve values present in both include and exclude for the same field.

    Exclude wins: the contradicting value is removed from include and kept in
    exclude. This preserves the operator's explicit exclusion intent and is
    consistent with AppNeta's evaluation order (include first, then exclude).
    """
    scalar_fields = [
        ("severity",               "severity"),
        ("noiseFilter",            "noise filter"),
        ("monitoringPointId",      "monitoring point ID"),
        ("monitoringPointName",    "monitoring point name (glob)"),
        ("monitoringPointType",    "monitoring point type"),
        ("monitoringPolicyId",     "policy ID"),
        ("monitoringPolicyGroupId","policy group ID"),
        ("alarmRuleId",            "alarm rule ID"),
        ("target",                 "target"),
    ]
    for field, label in scalar_fields:
        inc = include_block.get(field, [])
        exc = exclude_block.get(field, [])
        if not inc or not exc:
            continue
        dupes = set(inc) & set(exc)
        if not dupes:
            continue
        for val in sorted(dupes, key=str):
            errors.append({
                "org": org_name, "type": "contradiction",
                "value": f"{label}: {val}",
                "note": "same value in both include and exclude — removed from include, kept in exclude",
            })
        include_block[field] = [v for v in inc if v not in dupes]
        if not include_block[field]:
            del include_block[field]

    inc_tags = include_block.get("tag", [])
    exc_tags = exclude_block.get("tag", [])
    # Tags: for each contradicting pair, the side with MORE values for that key is
    # the "list"; the other side holds the exception. Remove from the list side,
    # keep on the exception side. Equal counts default to exclude winning.
    if inc_tags and exc_tags:
        inc_set = {(t["category"], t["value"]) for t in inc_tags}
        exc_set = {(t["category"], t["value"]) for t in exc_tags}
        dupes = inc_set & exc_set
        if dupes:
            remove_from_inc: set = set()
            remove_from_exc: set = set()
            for cat, val in sorted(dupes):
                inc_others = sum(1 for t in inc_tags if t["category"] == cat and t["value"] != val)
                exc_others = sum(1 for t in exc_tags if t["category"] == cat and t["value"] != val)
                if inc_others == exc_others:
                    remove_from_inc.add((cat, val))
                    errors.append({
                        "org": org_name, "type": "conflict",
                        "value": f"tag: {cat}:{val}",
                        "note": f"'{cat}:{val}' appears in both include and exclude with no clear list/exception distinction — remove it from one side",
                    })
                elif exc_others > inc_others:
                    remove_from_exc.add((cat, val))
                    errors.append({
                        "org": org_name, "type": "contradiction",
                        "value": f"tag: {cat}:{val}",
                        "note": f"tag key '{cat}' has more values in exclude — '{val}' is the include exception; removed from exclude, kept in include",
                    })
                else:
                    remove_from_inc.add((cat, val))
                    errors.append({
                        "org": org_name, "type": "contradiction",
                        "value": f"tag: {cat}:{val}",
                        "note": f"tag key '{cat}' has more values in include — '{val}' is the exclude exception; removed from include, kept in exclude",
                    })
            include_block["tag"] = [t for t in inc_tags if (t["category"], t["value"]) not in remove_from_inc]
            exclude_block["tag"] = [t for t in exc_tags if (t["category"], t["value"]) not in remove_from_exc]
            if not include_block["tag"]:
                del include_block["tag"]
            if not exclude_block["tag"]:
                del exclude_block["tag"]


def build_payload(config: dict, client: "AppNetaClient", errors: list) -> dict:
    """Build the alarm connector payload dict from a config dict and a live API client.

    config keys used:
      connector.name, connector.description, connector.enabled, connector.id
      include.*, exclude.*       — filter blocks
      notify_on                  — list of event types
      webhook.url, webhook.method, webhook.ignore_ssl_errors
      webhook.headers            — list of {key, value} dicts
      webhook.auth.type          — NONE, BASIC, or BEARER
      webhook.auth.username      — BASIC only
      webhook.auth.password      — BASIC only (passed as a plain value)
      webhook.auth.token         — BEARER only (passed as a plain value)
    """
    include_section = config.get("include", {})
    exclude_section = dict(config.get("exclude", {}))

    include_block = build_filter(include_section, client, errors)
    exclude_block = build_filter(exclude_section, client, errors)

    _remove_contradictions(include_block, exclude_block, errors, client.org_name)

    webhook = config.get("webhook", {})
    connector_entry: dict[str, Any] = {
        "type": "WEBHOOK",
        "url": webhook["url"],
        "method": webhook.get("method", "POST").upper(),
    }
    if webhook.get("headers"):
        connector_entry["headers"] = [
            {"key": h.get("key") or h["name"], "value": h["value"]}
            for h in webhook["headers"]
        ]
    auth = webhook.get("auth", {})
    auth_type = auth.get("type", "NONE").upper()
    if auth_type != "NONE":
        auth_block: dict[str, str] = {"type": auth_type}
        if auth_type == "BASIC":
            if auth.get("username"):
                auth_block["username"] = auth["username"]
            if auth.get("password"):
                auth_block["password"] = auth["password"]
        elif auth_type == "BEARER" and auth.get("token"):
            auth_block["token"] = auth["token"]
        connector_entry["auth"] = auth_block
    if webhook.get("ignore_ssl_errors"):
        connector_entry["ignoreSSLErrors"] = True

    connector_cfg = config.get("connector", {})
    payload: dict[str, Any] = {
        "name": connector_cfg["name"],
        "enabled": connector_cfg.get("enabled", True),
    }
    if connector_cfg.get("description"):
        payload["description"] = connector_cfg["description"]
    if include_block:
        payload["include"] = include_block
    if exclude_block:
        payload["exclude"] = exclude_block

    payload["notifyOn"] = [n.upper() for n in config.get("notify_on", ["ALARM_RAISED", "ALARM_CLEARED"])]
    payload["connectors"] = [connector_entry]
    return payload
