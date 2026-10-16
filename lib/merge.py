"""Connector diff and merge helpers for UPDATE (PUT) mode."""

import json
from typing import Any

from payload import _remove_contradictions


def _diff_field(path: str, current: Any, proposed: Any, lines: list[str]) -> None:
    """Recursively collect human-readable diff lines for changed fields."""
    if current == proposed:
        return
    if isinstance(current, str) and current and all(c == "*" for c in current):
        lines.append(f"  ? {path}: (masked in existing connector — cannot verify if value changed)")
        return
    if isinstance(current, dict) and isinstance(proposed, dict):
        for k in sorted(set(current) | set(proposed)):
            _diff_field(f"{path}.{k}", current.get(k), proposed.get(k), lines)
    elif isinstance(current, list) and isinstance(proposed, list):
        if all(isinstance(x, dict) for x in (current or []) + (proposed or [])):
            for i in range(max(len(current), len(proposed))):
                c = current[i] if i < len(current) else None
                p = proposed[i] if i < len(proposed) else None
                _diff_field(f"{path}[{i}]", c, p, lines)
        elif current != proposed:
            lines.append(f"  ~ {path}: {json.dumps(current)} → {json.dumps(proposed)}")
    else:
        curr_s = json.dumps(current)
        prop_s = json.dumps(proposed)
        if current is None:
            lines.append(f"  + {path}: {prop_s}")
        elif proposed is None:
            lines.append(f"  - {path}: {curr_s}")
        else:
            lines.append(f"  ~ {path}: {curr_s[:80]} → {prop_s[:80]}")


def diff_connector(current: dict, proposed: dict) -> list[str]:
    lines: list[str] = []
    for key in ("name", "description", "enabled", "include", "exclude", "notifyOn", "connectors"):
        _diff_field(key, current.get(key), proposed.get(key), lines)
    return lines


def resolve_connector_mode(
    client: "AppNetaClient", config: dict
) -> tuple[str, int | None, dict | None]:
    """Determine payload type (CREATE vs UPDATE) from connector.id in config.

    If connector.id is set, attempts a read-only GET of the existing connector
    for merge and diff. Returns POST mode if no id is set.

    No write operations are performed — this is a read-only lookup.
    """
    connector_cfg = config.get("connector", {})
    explicit_id = connector_cfg.get("id")
    if explicit_id is None:
        return "POST", None, None
    existing = client.get_connector(int(explicit_id))
    return "PUT", int(explicit_id), existing


def merge_with_existing(payload: dict, existing: dict, errors: list | None = None, org_name: str = "") -> dict:
    """Merge a generated payload with the existing connector for UPDATE (PUT) mode.

    Semantics: fields present in the generated payload override the existing
    connector. Fields absent from the payload are preserved from the existing
    connector unchanged.

    To REMOVE a field entirely (e.g. clear all severity filters), DELETE the
    connector and re-create it with POST.

    Applied to:
    - include/exclude filter blocks — merged field-by-field
    - connectors list — matched by index. Only 'id' is carried over from the
      existing sub-connector (the API rejects a PUT whose entry is missing 'id':
      400 "Connector ID is required for update operations"). Everything else comes
      from the generated entry, so dropping auth or headers actually drops them
      and masked placeholders ("********") are never written back. If the existing
      entry bypassed TLS verification, ignoreSSLErrors is sent explicitly as false
      unless the generated entry sets it.
    - include/exclude contradictions the merge creates (e.g. the existing include
      holds a value the new exclude now names) are resolved exclude-wins and
      appended to `errors` when given.
    - description — preserved from existing when absent from payload
    """
    merged = dict(payload)

    for block_name in ("include", "exclude"):
        existing_block = existing.get(block_name, {})
        new_block = merged.get(block_name, {})
        if existing_block:
            merged_block = {**existing_block, **new_block}
            if merged_block:
                merged[block_name] = merged_block

    existing_conns = existing.get("connectors", [])
    new_conns = merged.get("connectors", [])
    if existing_conns and new_conns:
        merged_conns = []
        for i, new_conn in enumerate(new_conns):
            if i < len(existing_conns):
                mc = dict(new_conn)
                if "id" in existing_conns[i]:
                    mc.setdefault("id", existing_conns[i]["id"])
                if existing_conns[i].get("ignoreSSLErrors"):
                    mc.setdefault("ignoreSSLErrors", False)
            else:
                mc = dict(new_conn)
            merged_conns.append(mc)
        merged["connectors"] = merged_conns

    if merged.get("include") and merged.get("exclude"):
        _remove_contradictions(merged["include"], merged["exclude"],
                               errors if errors is not None else [], org_name)
        if not merged["include"]:
            del merged["include"]
        if not merged["exclude"]:
            del merged["exclude"]

    if "description" not in merged and existing.get("description"):
        merged["description"] = existing["description"]

    return merged
