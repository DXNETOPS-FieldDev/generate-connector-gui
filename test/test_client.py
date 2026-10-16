"""Tests for AppNetaClient HTTP layer (urllib mocked at boundary) and build_payload integration."""
import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from generate_connector import AppNetaAPIError, AppNetaAuthError, AppNetaNetworkError, AppNetaClient, build_payload
from client import _validate_base_url
from fixtures import MONITORING_POINTS, POLICIES


# ── Mock helpers ────────────────────────────────────────────────────────────────

def _make_response(data):
    """Context-manager mock for urllib.request.urlopen returning JSON data."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(data).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _http_error(code, msg="Error"):
    return urllib.error.HTTPError("http://x", code, msg, {}, None)


def _client(base_url="https://nis.example.com", api_key="test-key", org_id=18223, org_name="Test Org"):
    return AppNetaClient(base_url, api_key, org_id, org_name)


# ── list_organizations ───────────────────────────────────────────────────────────

class TestListOrganizations(unittest.TestCase):

    def test_returns_list_of_orgs(self):
        orgs = [{"id": 1, "parentId": 0, "name": "Acme"}]
        with patch("urllib.request.urlopen", return_value=_make_response(orgs)):
            result = AppNetaClient.list_organizations("https://nis.example.com", "key")
        self.assertEqual(result, orgs)

    def test_unwraps_data_envelope(self):
        orgs = [{"id": 1, "parentId": 0, "name": "Acme"}]
        with patch("urllib.request.urlopen", return_value=_make_response({"data": orgs})):
            result = AppNetaClient.list_organizations("https://nis.example.com", "key")
        self.assertEqual(result, orgs)

    def test_raises_on_empty_list(self):
        with patch("urllib.request.urlopen", return_value=_make_response([])):
            with self.assertRaises(AppNetaAPIError):
                AppNetaClient.list_organizations("https://nis.example.com", "key")

    def test_url_includes_limit_1000(self):
        orgs = [{"id": 1, "parentId": 0, "name": "Acme"}]
        with patch("urllib.request.urlopen", return_value=_make_response(orgs)) as mock_open:
            AppNetaClient.list_organizations("https://nis.example.com", "key")
        call_url = mock_open.call_args[0][0].full_url
        self.assertIn("limit=1000", call_url)


# ── HTTP error cases ─────────────────────────────────────────────────────────────

class TestHTTPErrors(unittest.TestCase):

    def setUp(self):
        self.client = _client()

    def test_401_raises_auth_error(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(401, "Unauthorized")):
            with self.assertRaises(AppNetaAuthError) as ctx:
                self.client.list_monitoring_points()
        self.assertIn("401", str(ctx.exception))

    def test_403_raises_auth_error_when_not_allowed(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(403, "Forbidden")):
            with self.assertRaises(AppNetaAuthError) as ctx:
                self.client.list_monitoring_points()
        self.assertIn("403", str(ctx.exception))

    def test_403_returns_none_when_allow_403(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(403, "Forbidden")):
            result = self.client._get("/some/path", allow_403=True)
        self.assertIsNone(result)

    def test_404_raises_api_error_when_not_allowed(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(404, "Not Found")):
            with self.assertRaises(AppNetaAPIError):
                self.client._get("/missing")

    def test_404_returns_none_when_allow_404(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(404, "Not Found")):
            result = self.client._get("/missing", allow_404=True)
        self.assertIsNone(result)

    def test_500_raises_api_error(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(500, "Server Error")):
            with self.assertRaises(AppNetaAPIError):
                self.client._get("/path")

    def test_url_error_raises_network_error(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
            with self.assertRaises(AppNetaNetworkError):
                self.client._get("/path")

    def test_timeout_raises_network_error(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError(TimeoutError())):
            with self.assertRaises(AppNetaNetworkError) as ctx:
                self.client._get("/path")
        self.assertIn("timed out", str(ctx.exception).lower())


# ── List methods and caching ──────────────────────────────────────────────────────

class TestListMethods(unittest.TestCase):

    def setUp(self):
        self.client = _client()

    def test_list_monitoring_points_returns_list(self):
        with patch("urllib.request.urlopen", return_value=_make_response(MONITORING_POINTS)):
            result = self.client.list_monitoring_points()
        self.assertEqual(result, MONITORING_POINTS)

    def test_list_monitoring_points_caches_result(self):
        with patch("urllib.request.urlopen", return_value=_make_response(MONITORING_POINTS)) as mock_open:
            self.client.list_monitoring_points()
            self.client.list_monitoring_points()
        self.assertEqual(mock_open.call_count, 1)

    def test_list_monitoring_policies_returns_list(self):
        with patch("urllib.request.urlopen", return_value=_make_response(POLICIES)):
            result = self.client.list_monitoring_policies()
        self.assertEqual(result, POLICIES)

    def test_list_monitoring_policy_groups_returns_list(self):
        groups = [{"id": 300, "name": "Southwest Desert"}]
        with patch("urllib.request.urlopen", return_value=_make_response(groups)):
            result = self.client.list_monitoring_policy_groups()
        self.assertEqual(result, groups)

    def test_list_tags_returns_list(self):
        tags = [{"id": 1, "orgId": 18223, "category": "Location", "value": "Chicago IL"}]
        with patch("urllib.request.urlopen", return_value=_make_response(tags)):
            result = self.client.list_tags()
        self.assertEqual(result, tags)

    def test_list_monitoring_points_url_includes_org_id(self):
        with patch("urllib.request.urlopen", return_value=_make_response([])) as mock_open:
            self.client.list_monitoring_points()
        call_url = mock_open.call_args[0][0].full_url
        self.assertIn(str(self.client.org_id), call_url)


# ── get_connector ─────────────────────────────────────────────────────────────────

class TestGetConnector(unittest.TestCase):

    def setUp(self):
        self.client = _client()

    def test_returns_matching_connector(self):
        connector = {"id": 42, "name": "My Connector"}
        with patch("urllib.request.urlopen", return_value=_make_response([connector])):
            result = self.client.get_connector(42)
        self.assertEqual(result, connector)

    def test_returns_none_when_id_not_in_list(self):
        with patch("urllib.request.urlopen", return_value=_make_response([])):
            result = self.client.get_connector(99)
        self.assertIsNone(result)

    def test_returns_none_on_403(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(403, "Forbidden")):
            result = self.client.get_connector(42)
        self.assertIsNone(result)

    def test_caches_result(self):
        connector = {"id": 42, "name": "My Connector"}
        with patch("urllib.request.urlopen", return_value=_make_response([connector])) as mock_open:
            self.client.get_connector(42)
            self.client.get_connector(42)
        self.assertEqual(mock_open.call_count, 1)


# ── group_ids_for_names ───────────────────────────────────────────────────────────

class TestGroupIdsForNames(unittest.TestCase):

    GROUPS = [
        {"id": 300, "name": "Southwest Desert"},
        {"id": 301, "name": "Canyon Operations"},
    ]

    def setUp(self):
        self.client = _client()

    def test_name_resolves_to_id(self):
        errors = []
        with patch("urllib.request.urlopen", return_value=_make_response(self.GROUPS)):
            result = self.client.group_ids_for_names(["Southwest Desert"], errors)
        self.assertEqual(result, [300])
        self.assertEqual(errors, [])

    def test_case_insensitive_match(self):
        errors = []
        with patch("urllib.request.urlopen", return_value=_make_response(self.GROUPS)):
            result = self.client.group_ids_for_names(["southwest desert"], errors)
        self.assertEqual(result, [300])
        self.assertEqual(errors, [])

    def test_multiple_names_resolved(self):
        errors = []
        with patch("urllib.request.urlopen", return_value=_make_response(self.GROUPS)):
            result = self.client.group_ids_for_names(["Southwest Desert", "Canyon Operations"], errors)
        self.assertEqual(sorted(result), [300, 301])
        self.assertEqual(errors, [])

    def test_unknown_name_appends_error(self):
        errors = []
        with patch("urllib.request.urlopen", return_value=_make_response(self.GROUPS)):
            result = self.client.group_ids_for_names(["Nonexistent Group"], errors)
        self.assertEqual(result, [])
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["value"], "Nonexistent Group")
        self.assertEqual(errors[0]["org"], self.client.org_name)

    def test_error_includes_available_names(self):
        errors = []
        with patch("urllib.request.urlopen", return_value=_make_response(self.GROUPS)):
            self.client.group_ids_for_names(["Missing"], errors)
        self.assertIn("Southwest Desert", errors[0]["available"])


# ── base_url validation ───────────────────────────────────────────────────────────

class TestBaseURLValidation(unittest.TestCase):

    def test_valid_https_hostname(self):
        _validate_base_url("https://nis.example.com")

    def test_valid_https_with_port(self):
        _validate_base_url("https://nis.example.com:8443")

    def test_rejects_http_scheme(self):
        with self.assertRaises(ValueError) as ctx:
            _validate_base_url("http://nis.example.com")
        self.assertIn("https", str(ctx.exception))

    def test_allows_ip_literal(self):
        # On-prem AppNeta deployments are commonly reached via a private IP
        # with no DNS entry. base_url is operator-supplied trusted config,
        # not third-party input, so IP literals are intentionally allowed.
        _validate_base_url("https://10.0.0.1")

    def test_allows_ipv6_literal(self):
        _validate_base_url("https://[::1]")

    def test_rejects_path_component(self):
        with self.assertRaises(ValueError) as ctx:
            _validate_base_url("https://nis.example.com/some/path")
        self.assertIn("path", str(ctx.exception))

    def test_rejects_empty_url(self):
        with self.assertRaises(ValueError):
            _validate_base_url("")

    def test_constructor_rejects_invalid_url(self):
        with self.assertRaises(ValueError):
            AppNetaClient("http://nis.example.com", "key", 1, "Org")

    def test_list_organizations_rejects_invalid_url(self):
        with self.assertRaises(ValueError):
            AppNetaClient.list_organizations("http://nis.example.com", "key")


# ── URL construction ──────────────────────────────────────────────────────────────

class TestURLConstruction(unittest.TestCase):

    def test_trailing_slash_stripped_from_base_url(self):
        client = AppNetaClient("https://nis.example.com/", "key", 1, "Org")
        with patch("urllib.request.urlopen", return_value=_make_response([])) as mock_open:
            client.list_monitoring_points()
        call_url = mock_open.call_args[0][0].full_url
        self.assertNotIn("//api", call_url)
        self.assertIn("/api/v4/monitoringPoint", call_url)

    def test_authorization_header_uses_token_scheme(self):
        client = _client(api_key="my-secret-key")
        with patch("urllib.request.urlopen", return_value=_make_response([])) as mock_open:
            client.list_monitoring_points()
        req = mock_open.call_args[0][0]
        self.assertEqual(req.get_header("Authorization"), "Token my-secret-key")


# ── build_payload integration ─────────────────────────────────────────────────────

class TestBuildPayloadIntegration(unittest.TestCase):
    """End-to-end payload building with a mock client — no live API calls."""

    def _mock_client(self, points=None, policies=None, groups=None, tags=None):
        client = MagicMock()
        client.org_name = "Test Org"
        client.list_monitoring_points.return_value = points or []
        client.list_monitoring_policies.return_value = policies or []
        client.list_monitoring_policy_groups.return_value = groups or []
        client.list_tags.return_value = tags or []
        client.group_ids_for_names.return_value = []
        return client

    def _base_config(self, **overrides):
        config = {
            "connector": {"name": "Test Connector", "enabled": True},
            "webhook": {"url": "https://hooks.example.com/appneta", "method": "POST"},
        }
        config.update(overrides)
        return config

    def test_minimal_payload_structure(self):
        client = self._mock_client()
        errors = []
        payload = build_payload(self._base_config(), client, errors)
        self.assertEqual(payload["name"], "Test Connector")
        self.assertEqual(payload["enabled"], True)
        self.assertIn("connectors", payload)
        self.assertEqual(payload["connectors"][0]["url"], "https://hooks.example.com/appneta")
        self.assertEqual(errors, [])

    def test_notify_on_defaults_to_both_events(self):
        client = self._mock_client()
        payload = build_payload(self._base_config(), client, [])
        self.assertCountEqual(payload["notifyOn"], ["ALARM_RAISED", "ALARM_CLEARED"])

    def test_custom_notify_on(self):
        config = self._base_config(notify_on=["ALARM_RAISED"])
        payload = build_payload(config, self._mock_client(), [])
        self.assertEqual(payload["notifyOn"], ["ALARM_RAISED"])

    def test_description_included_when_present(self):
        config = self._base_config()
        config["connector"]["description"] = "Sends to Splunk"
        payload = build_payload(config, self._mock_client(), [])
        self.assertEqual(payload["description"], "Sends to Splunk")

    def test_description_absent_when_empty(self):
        payload = build_payload(self._base_config(), self._mock_client(), [])
        self.assertNotIn("description", payload)

    def test_mp_names_resolved_to_ids(self):
        client = self._mock_client(points=MONITORING_POINTS)
        config = self._base_config(include={"monitoring_point_names": ["ACME-MP-MesaFlats"]})
        errors = []
        payload = build_payload(config, client, errors)
        self.assertIn("include", payload)
        self.assertIn(100, payload["include"]["monitoringPointId"])
        self.assertEqual(errors, [])

    def test_unknown_mp_name_produces_error_not_exception(self):
        client = self._mock_client(points=MONITORING_POINTS)
        config = self._base_config(include={"monitoring_point_names": ["DOES-NOT-EXIST"]})
        errors = []
        payload = build_payload(config, client, errors)
        self.assertEqual(len(errors), 1)
        self.assertNotIn("include", payload)

    def test_glob_mp_name_passed_through_as_name_not_id(self):
        client = self._mock_client(points=MONITORING_POINTS)
        config = self._base_config(include={"monitoring_point_names": ["ACME-*"]})
        payload = build_payload(config, client, [])
        self.assertIn("monitoringPointName", payload["include"])
        self.assertNotIn("monitoringPointId", payload.get("include", {}))

    def test_severity_filter_uppercased(self):
        config = self._base_config(include={"severity": ["critical", "major"]})
        payload = build_payload(config, self._mock_client(), [])
        self.assertCountEqual(payload["include"]["severity"], ["CRITICAL", "MAJOR"])

    def test_monitoring_point_ids_single_value_passthrough(self):
        config = self._base_config(include={"monitoring_point_ids": 100})
        payload = build_payload(config, self._mock_client(), [])
        self.assertEqual(payload["include"]["monitoringPointId"], [100])

    def test_monitoring_point_ids_list_passthrough(self):
        config = self._base_config(include={"monitoring_point_ids": [100, 101]})
        payload = build_payload(config, self._mock_client(), [])
        self.assertEqual(payload["include"]["monitoringPointId"], [100, 101])

    def test_monitoring_policy_ids_passthrough(self):
        config = self._base_config(include={"monitoring_policy_ids": [200]})
        payload = build_payload(config, self._mock_client(), [])
        self.assertEqual(payload["include"]["monitoringPolicyId"], [200])

    def test_monitoring_policy_group_ids_passthrough(self):
        config = self._base_config(include={"monitoring_policy_group_ids": [300]})
        payload = build_payload(config, self._mock_client(), [])
        self.assertEqual(payload["include"]["monitoringPolicyGroupId"], [300])

    def test_id_not_in_live_catalog_is_accepted_without_error(self):
        # Dedicated ID fields are a direct passthrough with no API lookup --
        # unlike monitoring_point_names' numeric passthrough, which validates
        # membership via resolve_to_ids and errors on an unknown ID.
        client = self._mock_client(points=MONITORING_POINTS)
        config = self._base_config(include={"monitoring_point_ids": [999999]})
        errors = []
        payload = build_payload(config, client, errors)
        self.assertEqual(payload["include"]["monitoringPointId"], [999999])
        self.assertEqual(errors, [])

    def test_merges_with_names_field_numeric_passthrough(self):
        client = self._mock_client(points=MONITORING_POINTS)
        config = self._base_config(include={
            "monitoring_point_names": ["ACME-MP-MesaFlats"],  # resolves to 100
            "monitoring_point_ids": [999],
        })
        payload = build_payload(config, client, [])
        self.assertEqual(sorted(payload["include"]["monitoringPointId"]), [100, 999])

    def test_duplicate_id_across_both_mechanisms_is_deduplicated(self):
        client = self._mock_client(points=MONITORING_POINTS)
        config = self._base_config(include={
            "monitoring_point_names": ["ACME-MP-MesaFlats"],  # resolves to 100
            "monitoring_point_ids": [100],
        })
        payload = build_payload(config, client, [])
        self.assertEqual(payload["include"]["monitoringPointId"], [100])

    def test_non_integer_in_list_is_silently_skipped(self):
        config = self._base_config(include={"monitoring_point_ids": [100, "bad", -5, 0]})
        payload = build_payload(config, self._mock_client(), [])
        self.assertEqual(payload["include"]["monitoringPointId"], [100])

    def test_absent_id_fields_produce_no_key(self):
        payload = build_payload(self._base_config(), self._mock_client(), [])
        self.assertNotIn("include", payload)

    def test_webhook_bearer_auth_included(self):
        config = self._base_config()
        config["webhook"]["auth"] = {"type": "BEARER", "token": "mytoken"}
        payload = build_payload(config, self._mock_client(), [])
        auth = payload["connectors"][0]["auth"]
        self.assertEqual(auth["type"], "BEARER")
        self.assertEqual(auth["token"], "mytoken")

    def test_webhook_basic_auth_included(self):
        config = self._base_config()
        config["webhook"]["auth"] = {"type": "BASIC", "username": "user", "password": "pass"}
        payload = build_payload(config, self._mock_client(), [])
        auth = payload["connectors"][0]["auth"]
        self.assertEqual(auth["type"], "BASIC")
        self.assertEqual(auth["username"], "user")

    def test_webhook_none_auth_no_auth_block(self):
        config = self._base_config()
        config["webhook"]["auth"] = {"type": "NONE"}
        payload = build_payload(config, self._mock_client(), [])
        self.assertNotIn("auth", payload["connectors"][0])

    def test_custom_headers_included(self):
        config = self._base_config()
        config["webhook"]["headers"] = [{"key": "X-Token", "value": "abc"}]
        payload = build_payload(config, self._mock_client(), [])
        headers = payload["connectors"][0]["headers"]
        self.assertEqual(headers[0]["key"], "X-Token")
        self.assertEqual(headers[0]["value"], "abc")

    def test_ignore_ssl_errors_included(self):
        config = self._base_config()
        config["webhook"]["ignore_ssl_errors"] = True
        payload = build_payload(config, self._mock_client(), [])
        self.assertTrue(payload["connectors"][0]["ignoreSSLErrors"])

    def test_contradiction_between_include_and_exclude_removed(self):
        config = self._base_config(
            include={"severity": ["CRITICAL", "MAJOR"]},
            exclude={"severity": ["MAJOR"]},
        )
        errors = []
        payload = build_payload(config, self._mock_client(), errors)
        self.assertNotIn("MAJOR", payload.get("include", {}).get("severity", []))
        self.assertIn("MAJOR", payload.get("exclude", {}).get("severity", []))
        self.assertTrue(any("contradiction" in str(e) for e in errors))

    def test_policy_names_resolved_to_ids(self):
        client = self._mock_client(policies=POLICIES)
        config = self._base_config(include={"monitoring_policy_names": ["Southwest Desert"]})
        payload = build_payload(config, client, [])
        self.assertIn(200, payload["include"]["monitoringPolicyId"])

    def test_empty_include_block_omitted_from_payload(self):
        config = self._base_config(include={})
        payload = build_payload(config, self._mock_client(), [])
        self.assertNotIn("include", payload)

    def test_empty_exclude_block_omitted_from_payload(self):
        config = self._base_config(exclude={})
        payload = build_payload(config, self._mock_client(), [])
        self.assertNotIn("exclude", payload)


if __name__ == "__main__":
    unittest.main()
