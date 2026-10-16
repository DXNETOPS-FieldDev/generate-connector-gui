"""
AppNeta Alarm Connector — compatibility shim.

Re-exports the full public API from the split submodules. Add shared/lib to
sys.path, then import from this module for backward compatibility, or import
directly from the specific submodule for new code.

  from generate_connector import AppNetaClient, build_payload, validate_request
  # or, for new code:
  from client import AppNetaClient
  from payload import build_payload
  from validation import validate_request
"""

from client import AppNetaAPIError, AppNetaAuthError, AppNetaNetworkError, AppNetaClient
from constants import (
    VALID_SEVERITIES, VALID_NOISE_FILTERS, VALID_NOTIFY_ON,
    VALID_METHODS, VALID_AUTH_TYPES, _GLOB_CHARS, _MP_TYPE_ALIASES,
)
from merge import _diff_field, diff_connector, merge_with_existing, resolve_connector_mode
from org_helpers import build_org_tree, find_org_root, resolve_orgs, root_orgs, validate_same_hierarchy
from payload import _remove_contradictions, build_filter, build_payload
from resolution import (
    _fetch_tag_catalog, _has_glob, is_numeric,
    parse_tag_spec, resolve_mp_types, resolve_tags, resolve_to_ids,
)
from validation import validate_request

# ---------------------------------------------------------------------------
# Backward-compatible aliases for formerly-private org helper names.
# New code should use the public names above.
# ---------------------------------------------------------------------------
_root_orgs               = root_orgs
_find_org_root           = find_org_root
_validate_same_hierarchy = validate_same_hierarchy
_build_org_tree          = build_org_tree
_resolve_orgs            = resolve_orgs
