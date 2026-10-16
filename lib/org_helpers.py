"""Org tree discovery and restriction helpers."""


def root_orgs(orgs: list[dict]) -> list[dict]:
    """Return orgs that are top-level within the result set (parentId not present in set)."""
    id_set = {o["id"] for o in orgs}
    return [o for o in orgs if o.get("parentId", 0) not in id_set]


def find_org_root(org_id: int, org_by_id: dict[int, dict], id_set: set[int]) -> int:
    """Walk parentId chain to find the root org ID for a given org."""
    current = org_id
    visited: set[int] = set()
    while current not in visited:
        visited.add(current)
        org = org_by_id.get(current)
        if org is None:
            break
        pid = org.get("parentId", 0)
        if pid not in id_set:
            break
        current = pid
    return current


def validate_same_hierarchy(selected: list[dict], all_orgs: list[dict]) -> tuple[bool, str]:
    """Verify all selected orgs share the same root in the full org list."""
    if len(selected) <= 1:
        return True, ""
    id_set = {o["id"] for o in all_orgs}
    org_by_id = {o["id"]: o for o in all_orgs}
    roots = {find_org_root(o["id"], org_by_id, id_set) for o in selected}
    if len(roots) == 1:
        return True, ""
    root_names = []
    for rid in sorted(roots):
        rorg = org_by_id.get(rid)
        root_names.append(f"{rorg['name']} (id={rid})" if rorg else str(rid))
    return False, (
        f"Specified orgs span {len(roots)} unrelated customer hierarchies: "
        + ", ".join(root_names)
        + "\n  All org IDs must belong to the same customer hierarchy."
    )


def build_org_tree(orgs: list[dict]) -> str:
    """Render the org list as an indented tree using parentId relationships."""
    id_set = {o["id"] for o in orgs}
    by_parent: dict[int, list[dict]] = {}
    for o in orgs:
        pid = o.get("parentId", 0)
        if pid not in id_set:
            pid = 0
        by_parent.setdefault(pid, []).append(o)

    lines: list[str] = []

    def _render(parent_id: int, indent: str) -> None:
        children = sorted(by_parent.get(parent_id, []), key=lambda o: o["id"])
        for i, org in enumerate(children):
            is_last = i == len(children) - 1
            branch = "└─ " if is_last else "├─ "
            lines.append(f"    {org['id']:>6}  {indent}{branch}{org['name']}")
            _render(org["id"], indent + ("   " if is_last else "│  "))

    for root in sorted(by_parent.get(0, []), key=lambda o: o["id"]):
        lines.append(f"    {root['id']:>6}  {root['name']}")
        _render(root["id"], "")

    return "\n".join(lines)


def resolve_orgs(all_orgs: list[dict], specs: list) -> tuple[list[dict], list[str]]:
    """Resolve a list of org specs (int ID, numeric string, or name substring) to org objects.

    Each spec is resolved independently:
      - Integer or numeric string → exact org ID match
      - Non-numeric string → case-insensitive substring match on name (must be unambiguous)

    Returns (matched_orgs, error_messages). Duplicates are silently collapsed.
    """
    seen_ids: set[int] = set()
    matched: list[dict] = []
    errors: list[str] = []

    for spec in specs:
        spec_s = str(spec).strip()
        if isinstance(spec, int) or spec_s.lstrip("-").isdigit():
            target_id = int(spec_s)
            org = next((o for o in all_orgs if o["id"] == target_id), None)
            if org is None:
                errors.append(
                    f"Org ID {target_id} not found in API response ({len(all_orgs)} orgs returned)"
                )
            elif target_id not in seen_ids:
                seen_ids.add(target_id)
                matched.append(org)
        else:
            needle = spec_s.lower()
            name_matches = [o for o in all_orgs if needle in o.get("name", "").lower()]
            if not name_matches:
                errors.append(f"No org matched name substring {spec_s!r}")
            elif len(name_matches) > 1:
                names = ", ".join(f"{o['name']} (id={o['id']})" for o in name_matches)
                errors.append(
                    f"Name substring {spec_s!r} is ambiguous — matched {len(name_matches)} orgs: {names}"
                )
            else:
                oid = name_matches[0]["id"]
                if oid not in seen_ids:
                    seen_ids.add(oid)
                    matched.append(name_matches[0])

    return matched, errors
