"""Flask route handler tests for the generate-connector blueprint.

Tests the validation and error-handling logic in connector_app.py.
All upstream API calls are patched at the connector_app module boundary.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

from generate_connector import AppNetaAPIError, AppNetaNetworkError
from connector_app import connector_bp


def _make_app():
    flask_app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    flask_app.secret_key = "test-secret-key-do-not-use"
    flask_app.config["TESTING"] = True
    flask_app.register_blueprint(connector_bp)
    return flask_app


def _valid_body(**overrides):
    body = {
        "api_key": "test-key",
        "base_url": "https://nis.example.com",
        "connector": {"name": "My Connector", "enabled": True},
        "webhook": {"url": "https://hooks.example.com/appneta", "method": "POST"},
    }
    body.update(overrides)
    return body


_SINGLE_ORG = [{"id": 42, "parentId": 0, "name": "Acme Corp"}]
_PAYLOAD = {
    "name": "My Connector",
    "enabled": True,
    "connectors": [{"url": "https://hooks.example.com/appneta", "method": "POST"}],
    "notifyOn": ["ALARM_RAISED", "ALARM_CLEARED"],
}


class TestGetConnectorRoute(unittest.TestCase):
    def setUp(self):
        self.client = _make_app().test_client()

    def test_returns_200(self):
        resp = self.client.get("/connector")
        self.assertEqual(resp.status_code, 200)

    def test_renders_html(self):
        resp = self.client.get("/connector")
        self.assertIn(b"connector", resp.data.lower())


class TestGenerateRouteInputValidation(unittest.TestCase):
    def setUp(self):
        self.client = _make_app().test_client()

    def _post(self, body=None, **kwargs):
        if body is None:
            return self.client.post("/api/connector/generate", **kwargs)
        return self.client.post(
            "/api/connector/generate",
            data=json.dumps(body),
            content_type="application/json",
        )

    def test_non_json_body_returns_400(self):
        resp = self.client.post("/api/connector/generate",
                                data="not json", content_type="text/plain")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("json", resp.get_json()["error"].lower())

    def test_empty_body_returns_400(self):
        resp = self.client.post("/api/connector/generate")
        self.assertEqual(resp.status_code, 400)

    def test_missing_base_url_returns_400(self):
        body = _valid_body()
        del body["base_url"]
        resp = self._post(body)
        self.assertEqual(resp.status_code, 400)

    def test_http_base_url_returns_400(self):
        resp = self._post(_valid_body(base_url="http://nis.example.com"))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("https", resp.get_json()["error"].lower())


    def test_base_url_with_path_returns_400(self):
        resp = self._post(_valid_body(base_url="https://nis.example.com/api"))
        self.assertEqual(resp.status_code, 400)

    def test_missing_api_key_returns_400(self):
        body = _valid_body()
        del body["api_key"]
        resp = self._post(body)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("api key", resp.get_json()["error"].lower())

    def test_empty_api_key_returns_400(self):
        resp = self._post(_valid_body(api_key=""))
        self.assertEqual(resp.status_code, 400)

    def test_missing_connector_name_returns_400(self):
        body = _valid_body()
        body["connector"] = {"enabled": True}
        resp = self._post(body)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("connector name", resp.get_json()["error"].lower())

    def test_empty_connector_name_returns_400(self):
        body = _valid_body()
        body["connector"] = {"name": "  ", "enabled": True}
        resp = self._post(body)
        self.assertEqual(resp.status_code, 400)

    def test_missing_webhook_url_returns_400(self):
        body = _valid_body()
        body["webhook"] = {"method": "POST"}
        resp = self._post(body)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("webhook", resp.get_json()["error"].lower())


class TestGenerateRouteAPIErrors(unittest.TestCase):
    def setUp(self):
        self.client = _make_app().test_client()

    def _post(self, body=None):
        return self.client.post(
            "/api/connector/generate",
            data=json.dumps(body or _valid_body()),
            content_type="application/json",
        )

    def test_network_error_returns_502(self):
        with patch("connector_app.AppNetaClient.list_organizations",
                   side_effect=AppNetaNetworkError("Network error reaching AppNeta server.")):
            resp = self._post()
        self.assertEqual(resp.status_code, 502)

    def test_api_error_returns_400(self):
        with patch("connector_app.AppNetaClient.list_organizations",
                   side_effect=AppNetaAPIError("No organizations returned.")):
            resp = self._post()
        self.assertEqual(resp.status_code, 400)

    def test_network_error_message_not_leaked(self):
        """Sanitized message returned — no internal hostnames."""
        with patch("connector_app.AppNetaClient.list_organizations",
                   side_effect=AppNetaNetworkError("Network error reaching AppNeta server.")):
            data = self._post().get_json()
        self.assertNotIn("nis.example.com", data.get("error", ""))

    def test_payload_build_network_error_returns_502(self):
        with patch("connector_app.AppNetaClient") as MockClient, \
             patch("connector_app.build_payload",
                   side_effect=AppNetaNetworkError("timeout")):
            MockClient.list_organizations.return_value = _SINGLE_ORG
            resp = self._post()
        self.assertEqual(resp.status_code, 502)

    def test_payload_build_api_error_returns_400(self):
        with patch("connector_app.AppNetaClient") as MockClient, \
             patch("connector_app.build_payload",
                   side_effect=AppNetaAPIError("403 Forbidden")):
            MockClient.list_organizations.return_value = _SINGLE_ORG
            resp = self._post()
        self.assertEqual(resp.status_code, 400)


class TestGenerateRouteSuccess(unittest.TestCase):
    def setUp(self):
        self.client = _make_app().test_client()

    def _post_with_mocks(self, body=None):
        with patch("connector_app.AppNetaClient") as MockClient, \
             patch("connector_app.build_payload", return_value=dict(_PAYLOAD)), \
             patch("connector_app.resolve_connector_mode",
                   return_value=("CREATE", None, None)):
            MockClient.list_organizations.return_value = _SINGLE_ORG
            resp = self.client.post(
                "/api/connector/generate",
                data=json.dumps(body or _valid_body()),
                content_type="application/json",
            )
        return resp

    def test_returns_200(self):
        self.assertEqual(self._post_with_mocks().status_code, 200)

    def test_response_contains_payloads_list(self):
        data = self._post_with_mocks().get_json()
        self.assertIn("payloads", data)
        self.assertEqual(len(data["payloads"]), 1)

    def test_payload_contains_connector_name(self):
        data = self._post_with_mocks().get_json()
        self.assertEqual(data["payloads"][0]["payload"]["name"], "My Connector")

    def test_mode_is_create_for_new_connector(self):
        data = self._post_with_mocks().get_json()
        self.assertEqual(data["mode"], "CREATE")

    def test_org_id_and_name_in_payload_entry(self):
        data = self._post_with_mocks().get_json()
        entry = data["payloads"][0]
        self.assertEqual(entry["org_id"], 42)
        self.assertEqual(entry["org_name"], "Acme Corp")


class TestConnectorDetailPreservesMask(unittest.TestCase):
    """The PUT auto-populate feature relies on AppNeta masking secrets as
    all-asterisks ('*'). The client-side JS keys off that sentinel to clear
    and red-flag masked fields. This guards that the detail route passes the
    mask through unchanged — if it ever stripped or altered it, the masking
    UX would break silently."""

    def setUp(self):
        self.client = _make_app().test_client()

    def _body(self, **overrides):
        body = {
            "base_url": "https://nis.example.com",
            "api_key": "test-key",
            "org_id": 42,
            "connector_id": 7,
        }
        body.update(overrides)
        return body

    def _post(self, body):
        return self.client.post(
            "/api/get/connector/detail",
            data=json.dumps(body),
            content_type="application/json",
        )

    _MASKED = {
        "id": 7,
        "name": "Existing Connector",
        "connectors": [{
            "url": "https://hooks.example.com/appneta",
            "method": "PUT",
            "auth": {"type": "BEARER", "token": "*"},
            "headers": [
                {"key": "X-Api-Key", "value": "*"},
                {"key": "X-Trace", "value": "on"},
            ],
        }],
    }

    def test_masked_token_passed_through_unchanged(self):
        with patch("connector_app.AppNetaClient._get", return_value=[dict(self._MASKED)]):
            data = self._post(self._body()).get_json()
        conn = data["connector"]["connectors"][0]
        self.assertEqual(conn["auth"]["token"], "*")

    def test_masked_header_value_passed_through_unchanged(self):
        with patch("connector_app.AppNetaClient._get", return_value=[dict(self._MASKED)]):
            data = self._post(self._body()).get_json()
        headers = data["connector"]["connectors"][0]["headers"]
        self.assertEqual(headers[0]["value"], "*")

    def test_unmasked_header_value_passed_through_unchanged(self):
        with patch("connector_app.AppNetaClient._get", return_value=[dict(self._MASKED)]):
            data = self._post(self._body()).get_json()
        headers = data["connector"]["connectors"][0]["headers"]
        self.assertEqual(headers[1]["value"], "on")


if __name__ == "__main__":
    unittest.main()
