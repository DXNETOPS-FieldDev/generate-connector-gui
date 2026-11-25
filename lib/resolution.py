"""Name/ID resolution helpers — monitoring points, policies, groups, tags, MP types."""

from typing import TYPE_CHECKING

from constants import _GLOB_CHARS, _MP_TYPE_ALIASES

if TYPE_CHECKING:
    from client import AppNetaClient


def is_numeric(value: str) -> bool:
    try:
        int(value)
        return True
    except ValueError:
        return False


def _has_glob(value: str) -> bool:
    return any(c in value for c in _GLOB_CHARS)


def parse_tag_spec(raw: str) -> tuple[str | None, str | None]:
    """Parse a tag spec into (category, value).

    "Location:Chicago IL"  → ("Location", "Chicago IL")  exact match
    "Location"            → ("Location", None)          category-only
    ":Chicago IL"         → (None, "Chicago IL")        value-only
    """
    raw = raw.strip()
    if ":" in raw:
        cat, _, val = raw.partition(":")
        return (cat.strip() or None, val.strip() or None)
    return (raw or None, None)


def _fetch_tag_catalog(client: "AppNetaClient") -> set[tuple[str, str]]:
    """Fetch all (category, value) tag pairs via /api/v3/tag.

    Handles both object form ({category, value} fields) and string form
    ("Category: Value" or "Category:Value"), since the API may return either.
    Spaces around the colon separator are stripped in both cases.
    """
    catalog: set[tuple[str, str]] = set()
    for t in client.list_tags():
        if isinstance(t, str):
            cat, _, val = t.partition(":")
            cat, val = cat.strip(), val.strip()
        else:
            cat = t.get("category", "").strip()
            val = t.get("value", "").strip()
        if cat and val:
            catalog.add((cat, val))
    return catalog


def resolve_tags(
    tag_specs: list[str],
    config_tags: list[dict],
    client: "AppNetaClient",
    errors: list,
) -> list[dict]:
    """Resolve and validate all tags against the org's tag catalog from /api/v3/tag.

    config_tags: [{category, value}] from the config — validated as exact pairs.
    tag_specs: "Cat:Val" (exact), "Cat" (all values), ":Val" (all categories).

    Only full key:value pairs found in the catalog are included in the output.
    Unrecognized tags are written to the errors list.
    """
    if not tag_specs and not config_tags:
        return []

    catalog = _fetch_tag_catalog(client)
    result: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _add(c: str, v: str) -> None:
        if (c, v) not in seen:
            seen.add((c, v))
            result.append({"category": c, "value": v})

    def _exact_error(cat: str, val: str) -> dict:
        cats_in_catalog = {c for c, _ in catalog}
        if cat.lower() in {c.lower() for c in cats_in_catalog}:
            return {
                "org": client.org_name, "type": "tag",
                "value": f"{cat}:{val}",
                "note": f"category '{cat}' exists but value '{val}' not found",
                "available": sorted(v for c, v in catalog if c.lower() == cat.lower()),
            }
        return {
            "org": client.org_name, "type": "tag",
            "value": f"{cat}:{val}",
            "note": f"category '{cat}' not found in tag catalog",
            "available": sorted(cats_in_catalog),
        }

    for t in config_tags:
        cat = t.get("category", "").strip()
        val = t.get("value", "").strip()
        if not cat or not val:
            continue
        match = next(((c, v) for c, v in catalog if c.lower() == cat.lower() and v.lower() == val.lower()), None)
        if match:
            _add(*match)
        else:
            errors.append(_exact_error(cat, val))

    for spec in tag_specs:
        cat, val = parse_tag_spec(spec)
        if cat and val:
            match = next(((c, v) for c, v in catalog if c.lower() == cat.lower() and v.lower() == val.lower()), None)
            if match:
                _add(*match)
            else:
                errors.append(_exact_error(cat, val))
        elif cat:
            matches = sorted((c, v) for c, v in catalog if c.lower() == cat.lower())
            if matches:
                for c, v in matches:
                    _add(c, v)
            else:
                errors.append({
                    "org": client.org_name, "type": "tag category", "value": cat,
                    "available": sorted({c for c, _ in catalog}),
                })
        elif val:
            matches = sorted((c, v) for c, v in catalog if v.lower() == val.lower())
            if matches:
                for c, v in matches:
                    _add(c, v)
            else:
                errors.append({
                    "org": client.org_name, "type": "tag value", "value": val,
                    "available": sorted({v for _, v in catalog}),
                })

    return result


def resolve_to_ids(
    raw_values: list[str],
    lookup: list[dict],
    name_field: str,
    id_field: str,
    label: str,
    errors: list,
    org_name: str,
) -> list[int]:
    """Mixed list of names/IDs → integer IDs. Appends to errors for unmatched values."""
    name_map = {item[name_field].strip().lower(): item[id_field] for item in lookup}
    id_set = {item[id_field] for item in lookup}
    available_names = sorted(name_map.keys())
    result: list[int] = []
    for raw in raw_values:
        raw = raw.strip()
        if is_numeric(raw):
            num_id = int(raw)
            if num_id in id_set:
                result.append(num_id)
            else:
                errors.append({"org": org_name, "type": label, "value": raw, "available": available_names[:30]})
        else:
            resolved = name_map.get(raw.lower())
            if resolved is not None:
                result.append(resolved)
            else:
                errors.append({"org": org_name, "type": label, "value": raw, "available": available_names[:30]})
    return result


def resolve_mp_types(raw_types: list[str], all_points: list[dict], errors: list, org_name: str) -> list[str]:
    """Resolve MP type specs to API values for monitoringPointType.

    Glob patterns (*, **, +, ?, !) are passed through as-is — the API interprets them.
    Plain strings are substring-matched case-insensitively against live type names
    (e.g. 'c50' → 'c50 Container').
    """
    available = sorted({p.get("type", "") for p in all_points if p.get("type")})
    result: list[str] = []
    for raw in raw_types:
        raw = raw.strip()
        if _has_glob(raw):
            result.append(raw)
        elif raw.lower() in _MP_TYPE_ALIASES:
            result.extend(_MP_TYPE_ALIASES[raw.lower()])
        else:
            matches = [t for t in available if raw.lower() in t.lower()]
            if matches:
                result.extend(matches)
            else:
                errors.append({"org": org_name, "type": "MP type", "value": raw, "available": available})
    return list(dict.fromkeys(result))
