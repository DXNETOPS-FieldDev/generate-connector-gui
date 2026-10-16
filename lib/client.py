"""AppNeta API HTTP client (stdlib urllib only — no external dependencies)."""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


log = logging.getLogger(__name__)


class AppNetaAPIError(Exception):
    """Raised by AppNetaClient on API errors (replaces sys.exit in web context)."""


class AppNetaAuthError(AppNetaAPIError):
    """401 Unauthorized or 403 Forbidden from the AppNeta API."""


class AppNetaNetworkError(AppNetaAPIError):
    """Network connectivity or timeout error reaching the AppNeta server."""


def _validate_base_url(url: str) -> None:
    """Raise ValueError if url is not a safe HTTPS base URL.

    Blocks non-HTTPS schemes and embedded path components — callers must pass
    a scheme+host-only URL like https://nis.example.com or
    https://nis.example.com:8443.

    IP-literal hosts (e.g. https://192.0.2.10) are allowed deliberately:
    base_url is operator-supplied trusted config, not third-party input, and
    on-prem AppNeta deployments are commonly reached via a private IP with no
    DNS entry at all.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("base_url must use https://")
    if not parsed.hostname:
        raise ValueError("base_url must include a hostname")
    if parsed.path.rstrip("/"):
        raise ValueError("base_url must not include a path component")


class AppNetaClient:
    def __init__(self, base_url: str, api_key: str, org_id: int, org_name: str):
        _validate_base_url(base_url)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.org_id = org_id
        self.org_name = org_name
        self._cache: dict = {}

    @classmethod
    def list_organizations(cls, base_url: str, api_key: str) -> list[dict]:
        """Discover all organizations accessible to this API key.

        The endpoint defaults to limit=50; max is 1000.  Always request 1000
        to get the full list in a single call.
        """
        _validate_base_url(base_url)
        tmp = cls.__new__(cls)
        tmp.base_url = base_url.rstrip("/")
        tmp.api_key = api_key
        tmp.org_id = 0
        tmp.org_name = ""
        tmp._cache = {}
        orgs = tmp._unwrap(tmp._get("/v4/organization?limit=1000"))
        if not orgs:
            raise AppNetaAPIError(
                "No organizations returned — check the API key and permissions."
            )
        return orgs

    def _request(self, method: str, path: str, body: dict | None = None, allow_404: bool = False, allow_403: bool = False) -> Any:
        url = f"{self.base_url}/api{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers: dict[str, str] = {
            "Authorization": f"Token {self.api_key}",
            "Accept": "application/json",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 404 and allow_404:
                return None
            if e.code == 401:
                log.warning("AppNeta API 401 Unauthorized: %s", url)
                raise AppNetaAuthError("401 Unauthorized — check the API key.")
            if e.code == 403:
                if allow_403:
                    return None
                log.warning("AppNeta API 403 Forbidden: %s", url)
                raise AppNetaAuthError(
                    "403 Forbidden — API key does not have access to this endpoint. "
                    "Check that the key is scoped to the correct organization and has "
                    "at least read access to the required resources."
                )
            err_body = e.read().decode(errors="replace")
            log.warning("AppNeta API HTTP %d: %s — %s", e.code, url, err_body[:200])
            raise AppNetaAPIError(f"HTTP {e.code} error from AppNeta API.")
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError):
                log.warning("AppNeta API timeout: %s", url)
                raise AppNetaNetworkError("Request timed out reaching AppNeta server.")
            log.warning("AppNeta API network error: %s — %s", url, e.reason)
            raise AppNetaNetworkError("Network error reaching AppNeta server.")

    def _get(self, path: str, allow_404: bool = False, allow_403: bool = False) -> Any:
        return self._request("GET", path, allow_404=allow_404, allow_403=allow_403)

    def _unwrap(self, data: Any) -> list[dict]:
        if isinstance(data, list):
            return data
        if not isinstance(data, dict):
            return []
        for key in ("data", "items", "results"):
            if isinstance(data.get(key), list):
                return data[key]
        return []

    def _fetch_all_pages(self, base_path: str, limit: int = 1000) -> list[dict]:
        """Fetch all items from a paginated AppNeta v4 endpoint.

        Requests pages of `limit` items using offset-based pagination until a page
        smaller than `limit` is returned. AppNeta defaults to 50 items per page;
        the maximum is 1000. A safety cap of 100 pages prevents infinite loops if
        the API behaves unexpectedly.
        """
        results: list[dict] = []
        sep = "&" if "?" in base_path else "?"
        for page_num in range(100):
            offset = page_num * limit
            page = self._unwrap(
                self._get(f"{base_path}{sep}limit={limit}&offset={offset}")
            )
            results.extend(page)
            if len(page) < limit:
                break
        return results

    def list_monitoring_points(self) -> list[dict]:
        if "points" not in self._cache:
            self._cache["points"] = self._fetch_all_pages(
                f"/v4/monitoringPoint?orgId={self.org_id}"
            )
        return self._cache["points"]

    def list_monitoring_policies(self) -> list[dict]:
        if "policies" not in self._cache:
            self._cache["policies"] = self._fetch_all_pages(
                f"/v4/monitoringPolicy?orgId={self.org_id}"
            )
        return self._cache["policies"]

    def list_tags(self) -> list[dict]:
        if "tags" not in self._cache:
            self._cache["tags"] = self._fetch_all_pages(
                f"/v3/tag?orgId={self.org_id}"
            )
        return self._cache["tags"]

    def list_monitoring_policy_groups(self) -> list[dict]:
        if "groups" not in self._cache:
            self._cache["groups"] = self._fetch_all_pages(
                f"/v4/monitoringPolicyGroup?orgId={self.org_id}"
            )
        return self._cache["groups"]

    def get_connector(self, connector_id: int) -> dict | None:
        """Fetch a specific connector by ID using the ?id= query parameter.

        The v4 API does not support GET /v4/connector/alarm/{id} (returns 405).
        Instead, the connector list endpoint accepts ?id=<id> to filter by connector ID.
        Returns None if the connector is not found or if the request is not permitted.
        """
        cache_key = f"connector_{connector_id}"
        if cache_key not in self._cache:
            result = self._get(
                f"/v4/connector/alarm?orgId={self.org_id}&id={connector_id}",
                allow_403=True,
            )
            connectors = self._unwrap(result) if result is not None else None
            if connectors is None:
                self._cache[cache_key] = None
            else:
                self._cache[cache_key] = next(
                    (c for c in connectors if c.get("id") == connector_id), None
                )
        return self._cache[cache_key]

    def group_ids_for_names(self, group_names: list[str], errors: list) -> list[int]:
        """Return int64 global IDs for the given policy group name(s).

        Uses the dedicated /v4/monitoringPolicyGroup endpoint which returns
        groups with their own int64 global IDs directly.
        """
        groups = self.list_monitoring_policy_groups()
        lower_to_orig = {g.strip().lower(): g.strip() for g in group_names}
        available_names = sorted(grp["name"] for grp in groups if grp.get("name"))
        name_to_id: dict[str, int] = {}
        for grp in groups:
            name = grp.get("name", "").strip()
            gid = grp.get("id")
            if name and gid and name.lower() in lower_to_orig:
                name_to_id[name.lower()] = int(gid)
        unmatched = set(lower_to_orig.keys()) - name_to_id.keys()
        for lower_name in unmatched:
            errors.append({
                "org": self.org_name,
                "type": "policy group",
                "value": lower_to_orig[lower_name],
                "available": available_names,
            })
        return sorted(name_to_id.values())
