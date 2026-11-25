"""Tests for validate_request() — input validation before any API calls."""
import unittest
from typing import ClassVar

from generate_connector import validate_request


def _valid() -> dict:
    """Minimal valid request payload."""
    return {
        "connector": {"name": "Test Connector"},
        "webhook": {"url": "https://hooks.example.com/appneta", "method": "POST"},
    }


class TestValidateConnectorName(unittest.TestCase):

    def test_valid_payload_returns_no_errors(self):
        self.assertEqual(validate_request(_valid()), [])

    def test_missing_name_returns_error(self):
        data = _valid()
        data["connector"]["name"] = ""
        errors = validate_request(data)
        self.assertTrue(any("connector.name" in e for e in errors))

    def test_none_name_returns_error(self):
        data = _valid()
        data["connector"]["name"] = None
        errors = validate_request(data)
        self.assertTrue(any("connector.name" in e for e in errors))

    def test_name_too_long_returns_error(self):
        data = _valid()
        data["connector"]["name"] = "x" * 256
        errors = validate_request(data)
        self.assertTrue(any("connector.name" in e and "too long" in e for e in errors))

    def test_name_255_chars_is_valid(self):
        data = _valid()
        data["connector"]["name"] = "x" * 255
        self.assertEqual(validate_request(data), [])

    def test_name_with_null_byte_returns_error(self):
        data = _valid()
        data["connector"]["name"] = "Bad\x00Name"
        errors = validate_request(data)
        self.assertTrue(any("connector.name" in e and "control" in e for e in errors))

    def test_name_with_tab_is_valid(self):
        data = _valid()
        data["connector"]["name"] = "Name\twith\ttabs"
        self.assertEqual(validate_request(data), [])

    def test_name_with_crlf_returns_error(self):
        data = _valid()
        data["connector"]["name"] = "Test\r\nInjected"
        errors = validate_request(data)
        self.assertTrue(any("connector.name" in e and "control" in e for e in errors))

    def test_name_with_lone_lf_returns_error(self):
        data = _valid()
        data["connector"]["name"] = "Test\nNewline"
        errors = validate_request(data)
        self.assertTrue(any("connector.name" in e and "control" in e for e in errors))


class TestValidateConnectorDescription(unittest.TestCase):

    def test_absent_description_is_valid(self):
        self.assertEqual(validate_request(_valid()), [])

    def test_empty_description_is_valid(self):
        data = _valid()
        data["connector"]["description"] = ""
        self.assertEqual(validate_request(data), [])

    def test_description_too_long_returns_error(self):
        data = _valid()
        data["connector"]["description"] = "x" * 2001
        errors = validate_request(data)
        self.assertTrue(any("connector.description" in e and "too long" in e for e in errors))

    def test_description_2000_chars_is_valid(self):
        data = _valid()
        data["connector"]["description"] = "x" * 2000
        self.assertEqual(validate_request(data), [])

    def test_description_with_ctrl_char_returns_error(self):
        data = _valid()
        data["connector"]["description"] = "Bad\x01Desc"
        errors = validate_request(data)
        self.assertTrue(any("connector.description" in e and "control" in e for e in errors))


class TestValidateNotifyOn(unittest.TestCase):

    def test_valid_notify_on_values(self):
        data = _valid()
        data["notify_on"] = ["ALARM_RAISED", "ALARM_CLEARED"]
        self.assertEqual(validate_request(data), [])

    def test_single_valid_value(self):
        data = _valid()
        data["notify_on"] = ["ALARM_RAISED"]
        self.assertEqual(validate_request(data), [])

    def test_invalid_notify_on_returns_error(self):
        data = _valid()
        data["notify_on"] = ["ALARM_RAISED", "INVALID_EVENT"]
        errors = validate_request(data)
        self.assertTrue(any("notify_on" in e for e in errors))

    def test_empty_notify_on_is_rejected(self):
        # An explicit [] builds a connector that never fires; omit the key for the default.
        data = _valid()
        data["notify_on"] = []
        self.assertTrue(any("notify_on" in e for e in validate_request(data)))


class TestValidateSeverity(unittest.TestCase):

    def test_valid_include_severities(self):
        data = _valid()
        data["include"] = {"severity": ["CRITICAL", "MAJOR", "MINOR", "WARNING"]}
        self.assertEqual(validate_request(data), [])

    def test_invalid_include_severity_returns_error(self):
        data = _valid()
        data["include"] = {"severity": ["CRITICAL", "BOGUS"]}
        errors = validate_request(data)
        self.assertTrue(any("include.severity" in e for e in errors))

    def test_invalid_exclude_severity_returns_error(self):
        data = _valid()
        data["exclude"] = {"severity": ["NOTREAL"]}
        errors = validate_request(data)
        self.assertTrue(any("exclude.severity" in e for e in errors))

    def test_cleared_and_indeterminate_are_valid(self):
        data = _valid()
        data["include"] = {"severity": ["CLEARED", "INDETERMINATE"]}
        self.assertEqual(validate_request(data), [])


class TestValidateNoiseFilter(unittest.TestCase):

    def test_valid_noise_filter(self):
        data = _valid()
        data["include"] = {"noise_filter": ["FREQUENT"]}
        self.assertEqual(validate_request(data), [])

    def test_invalid_noise_filter_returns_error(self):
        data = _valid()
        data["include"] = {"noise_filter": ["RARE"]}
        errors = validate_request(data)
        self.assertTrue(any("include.noise_filter" in e for e in errors))


class TestValidateAlarmRuleIds(unittest.TestCase):

    def test_valid_positive_ids(self):
        data = _valid()
        data["include"] = {"alarm_rule_ids": [1, 42, 999]}
        self.assertEqual(validate_request(data), [])

    def test_zero_id_returns_error(self):
        data = _valid()
        data["include"] = {"alarm_rule_ids": [0]}
        errors = validate_request(data)
        self.assertTrue(any("alarm_rule_ids" in e for e in errors))

    def test_negative_id_returns_error(self):
        data = _valid()
        data["include"] = {"alarm_rule_ids": [-1]}
        errors = validate_request(data)
        self.assertTrue(any("alarm_rule_ids" in e for e in errors))

    def test_non_integer_id_returns_error(self):
        data = _valid()
        data["include"] = {"alarm_rule_ids": ["abc"]}
        errors = validate_request(data)
        self.assertTrue(any("alarm_rule_ids" in e for e in errors))

    def test_exclude_alarm_rule_ids_validated(self):
        data = _valid()
        data["exclude"] = {"alarm_rule_ids": [0]}
        errors = validate_request(data)
        self.assertTrue(any("exclude.alarm_rule_ids" in e for e in errors))


class TestValidateListFields(unittest.TestCase):

    FIELDS: ClassVar[list] = [
        "monitoring_point_names",
        "monitoring_point_types",
        "monitoring_policy_names",
        "monitoring_policy_group_names",
        "tags",
        "targets",
    ]

    def test_valid_string_lists_accepted(self):
        data = _valid()
        data["include"] = {f: ["value-a", "value-b"] for f in self.FIELDS}
        self.assertEqual(validate_request(data), [])

    def test_non_list_returns_error(self):
        data = _valid()
        data["include"] = {"monitoring_point_names": "not-a-list"}
        errors = validate_request(data)
        self.assertTrue(any("monitoring_point_names" in e and "must be a list" in e for e in errors))

    def test_non_string_item_returns_error(self):
        data = _valid()
        data["include"] = {"monitoring_point_names": [123]}
        errors = validate_request(data)
        self.assertTrue(any("monitoring_point_names" in e for e in errors))

    def test_item_with_ctrl_char_returns_error(self):
        data = _valid()
        data["include"] = {"tags": ["Bad\x01Tag"]}
        errors = validate_request(data)
        self.assertTrue(any("tags" in e and "control" in e for e in errors))

    def test_exclude_fields_also_validated(self):
        data = _valid()
        data["exclude"] = {"monitoring_point_names": 42}
        errors = validate_request(data)
        self.assertTrue(any("exclude.monitoring_point_names" in e for e in errors))


class TestValidateWebhook(unittest.TestCase):

    def test_missing_url_returns_error(self):
        data = _valid()
        data["webhook"]["url"] = ""
        errors = validate_request(data)
        self.assertTrue(any("webhook.url" in e and "required" in e for e in errors))

    def test_http_url_is_valid(self):
        data = _valid()
        data["webhook"]["url"] = "http://hooks.example.com/appneta"
        self.assertEqual(validate_request(data), [])

    def test_non_http_url_returns_error(self):
        data = _valid()
        data["webhook"]["url"] = "ftp://hooks.example.com/"
        errors = validate_request(data)
        self.assertTrue(any("webhook.url" in e for e in errors))

    def test_webhook_url_with_crlf_returns_error(self):
        data = _valid()
        data["webhook"]["url"] = "https://hooks.example.com/\r\nX-Evil: yes"
        errors = validate_request(data)
        self.assertTrue(any("webhook.url" in e and "control" in e for e in errors))

    def test_webhook_url_with_ctrl_char_returns_error(self):
        data = _valid()
        data["webhook"]["url"] = "https://hooks.example.com/\x01path"
        errors = validate_request(data)
        self.assertTrue(any("webhook.url" in e and "control" in e for e in errors))

    def test_valid_methods_accepted(self):
        for method in ("POST", "PUT", "GET", "PATCH", "DELETE", "HEAD"):
            data = _valid()
            data["webhook"]["method"] = method
            self.assertEqual(validate_request(data), [], msg=f"method={method}")

    def test_invalid_method_returns_error(self):
        data = _valid()
        data["webhook"]["method"] = "CONNECT"
        errors = validate_request(data)
        self.assertTrue(any("webhook.method" in e for e in errors))

    def test_valid_auth_types_accepted(self):
        for auth_type in ("NONE", "BASIC", "BEARER"):
            data = _valid()
            data["webhook"]["auth"] = {"type": auth_type}
            self.assertEqual(validate_request(data), [], msg=f"auth_type={auth_type}")

    def test_invalid_auth_type_returns_error(self):
        data = _valid()
        data["webhook"]["auth"] = {"type": "DIGEST"}
        errors = validate_request(data)
        self.assertTrue(any("webhook.auth.type" in e for e in errors))


class TestValidateWebhookHeaders(unittest.TestCase):

    def test_valid_header_accepted(self):
        data = _valid()
        data["webhook"]["headers"] = [{"key": "X-Token", "value": "abc123"}]
        self.assertEqual(validate_request(data), [])

    def test_headers_not_list_returns_error(self):
        data = _valid()
        data["webhook"]["headers"] = "Content-Type: application/json"
        errors = validate_request(data)
        self.assertTrue(any("webhook.headers" in e and "must be a list" in e for e in errors))

    def test_header_not_dict_returns_error(self):
        data = _valid()
        data["webhook"]["headers"] = ["Content-Type: application/json"]
        errors = validate_request(data)
        self.assertTrue(any("webhook.headers[0]" in e for e in errors))

    def test_empty_header_key_returns_error(self):
        data = _valid()
        data["webhook"]["headers"] = [{"key": "", "value": "val"}]
        errors = validate_request(data)
        self.assertTrue(any("webhook.headers[0].key" in e and "required" in e for e in errors))

    def test_header_key_with_space_returns_error(self):
        data = _valid()
        data["webhook"]["headers"] = [{"key": "X Bad Header", "value": "val"}]
        errors = validate_request(data)
        self.assertTrue(any("webhook.headers[0].key" in e and "invalid" in e for e in errors))

    def test_header_key_with_colon_returns_error(self):
        data = _valid()
        data["webhook"]["headers"] = [{"key": "X-Header:Bad", "value": "val"}]
        errors = validate_request(data)
        self.assertTrue(any("webhook.headers[0].key" in e and "invalid" in e for e in errors))

    def test_header_value_with_ctrl_char_returns_error(self):
        data = _valid()
        data["webhook"]["headers"] = [{"key": "X-Token", "value": "bad\x01value"}]
        errors = validate_request(data)
        self.assertTrue(any("webhook.headers[0].value" in e and "control" in e for e in errors))

    def test_header_value_with_crlf_returns_error(self):
        data = _valid()
        data["webhook"]["headers"] = [{"key": "X-Token", "value": "tok\r\nX-Evil: injected"}]
        errors = validate_request(data)
        self.assertTrue(any("webhook.headers[0].value" in e and "control" in e for e in errors))

    def test_header_key_with_crlf_returns_error(self):
        data = _valid()
        data["webhook"]["headers"] = [{"key": "X-Token\r\nEvil", "value": "val"}]
        errors = validate_request(data)
        self.assertTrue(any("webhook.headers[0].key" in e and "invalid" in e for e in errors))

    def test_multiple_headers_second_invalid_reported_correctly(self):
        data = _valid()
        data["webhook"]["headers"] = [
            {"key": "X-Good", "value": "ok"},
            {"key": "X Bad", "value": "val"},
        ]
        errors = validate_request(data)
        self.assertTrue(any("webhook.headers[1].key" in e for e in errors))
        self.assertFalse(any("webhook.headers[0]" in e for e in errors))

    def test_missing_key_field_returns_error(self):
        data = _valid()
        data["webhook"]["headers"] = [{"value": "val"}]
        errors = validate_request(data)
        self.assertTrue(any("webhook.headers[0].key" in e and "required" in e for e in errors))


class TestValidateWebhookAuthCredentials(unittest.TestCase):

    def test_bearer_token_without_crlf_is_valid(self):
        data = _valid()
        data["webhook"]["auth"] = {"type": "BEARER", "token": "mysecrettoken"}
        self.assertEqual(validate_request(data), [])

    def test_bearer_token_with_crlf_returns_error(self):
        data = _valid()
        data["webhook"]["auth"] = {"type": "BEARER", "token": "valid\r\nX-Injected: evil"}
        errors = validate_request(data)
        self.assertTrue(any("webhook.auth.token" in e and "control" in e for e in errors))

    def test_bearer_token_with_lone_lf_returns_error(self):
        data = _valid()
        data["webhook"]["auth"] = {"type": "BEARER", "token": "valid\nevil"}
        errors = validate_request(data)
        self.assertTrue(any("webhook.auth.token" in e and "control" in e for e in errors))

    def test_bearer_token_with_ctrl_char_returns_error(self):
        data = _valid()
        data["webhook"]["auth"] = {"type": "BEARER", "token": "tok\x01en"}
        errors = validate_request(data)
        self.assertTrue(any("webhook.auth.token" in e and "control" in e for e in errors))

    def test_basic_credentials_without_crlf_are_valid(self):
        data = _valid()
        data["webhook"]["auth"] = {"type": "BASIC", "username": "user", "password": "pass"}
        self.assertEqual(validate_request(data), [])

    def test_basic_username_with_crlf_returns_error(self):
        data = _valid()
        data["webhook"]["auth"] = {"type": "BASIC", "username": "user\r\nevil", "password": "pass"}
        errors = validate_request(data)
        self.assertTrue(any("webhook.auth.username" in e and "control" in e for e in errors))

    def test_basic_password_with_crlf_returns_error(self):
        data = _valid()
        data["webhook"]["auth"] = {"type": "BASIC", "username": "user", "password": "pass\r\nevil"}
        errors = validate_request(data)
        self.assertTrue(any("webhook.auth.password" in e and "control" in e for e in errors))

    def test_auth_credentials_not_validated_for_none_type(self):
        data = _valid()
        data["webhook"]["auth"] = {"type": "NONE"}
        self.assertEqual(validate_request(data), [])


class TestValidateNumericIdFields(unittest.TestCase):
    """monitoring_point_ids / monitoring_policy_ids / monitoring_policy_group_ids."""

    _FIELDS = ("monitoring_point_ids", "monitoring_policy_ids", "monitoring_policy_group_ids")

    def test_list_of_positive_ints_is_valid(self):
        for field in self._FIELDS:
            with self.subTest(field=field):
                data = _valid()
                data["include"] = {field: [2199023285464, 2199023289104]}
                self.assertEqual(validate_request(data), [])

    def test_single_bare_integer_is_valid(self):
        for field in self._FIELDS:
            with self.subTest(field=field):
                data = _valid()
                data["include"] = {field: 2199023285464}
                self.assertEqual(validate_request(data), [])

    def test_string_value_is_rejected(self):
        data = _valid()
        data["include"] = {"monitoring_point_ids": ["mp-site-a"]}
        errors = validate_request(data)
        self.assertEqual(len(errors), 1)
        self.assertIn("monitoring_point_ids", errors[0])

    def test_zero_is_rejected(self):
        data = _valid()
        data["include"] = {"monitoring_point_ids": [0]}
        errors = validate_request(data)
        self.assertEqual(len(errors), 1)
        self.assertIn("positive integer", errors[0])

    def test_negative_is_rejected(self):
        data = _valid()
        data["include"] = {"monitoring_point_ids": [-5]}
        errors = validate_request(data)
        self.assertEqual(len(errors), 1)

    def test_boolean_is_rejected(self):
        # bool is a subclass of int in Python -- True/False must not slip
        # through as 1/0.
        data = _valid()
        data["include"] = {"monitoring_point_ids": [True]}
        errors = validate_request(data)
        self.assertEqual(len(errors), 1)

    def test_non_list_non_int_is_rejected(self):
        data = _valid()
        data["include"] = {"monitoring_point_ids": {"foo": "bar"}}
        errors = validate_request(data)
        self.assertEqual(len(errors), 1)
        self.assertIn("must be an integer or a list of integers", errors[0])

    def test_works_on_exclude_block_too(self):
        data = _valid()
        data["exclude"] = {"monitoring_point_ids": [2199023285464]}
        self.assertEqual(validate_request(data), [])

    def test_mixed_valid_and_invalid_reports_the_invalid_one(self):
        data = _valid()
        data["include"] = {"monitoring_point_ids": [2199023285464, "bad"]}
        errors = validate_request(data)
        self.assertEqual(len(errors), 1)
        self.assertIn("bad", errors[0])


class TestValidateMultipleErrors(unittest.TestCase):

    def test_multiple_errors_all_returned(self):
        data = {
            "connector": {"name": ""},
            "webhook": {"url": "", "method": "INVALID"},
        }
        errors = validate_request(data)
        self.assertGreaterEqual(len(errors), 2)
        self.assertTrue(any("connector.name" in e for e in errors))
        self.assertTrue(any("webhook.url" in e for e in errors))


class TestReviewHardening(unittest.TestCase):
    """CRLF is checked on the raw value (not the stripped one), header names are RFC 7230 tokens,
    and nonsensical notify_on / connector.id values are rejected."""

    def _errs(self, mutate):
        data = _valid()
        mutate(data)
        return validate_request(data)

    def test_trailing_crlf_on_name_and_webhook_url_is_rejected(self):
        self.assertTrue(any("connector.name" in e for e in self._errs(lambda d: d["connector"].update(name="n\r\n"))))
        self.assertTrue(any("webhook.url" in e for e in self._errs(lambda d: d["webhook"].update(url="https://h.example.com\r\n"))))

    def test_del_character_is_a_control_character(self):
        self.assertTrue(any("connector.name" in e for e in self._errs(lambda d: d["connector"].update(name="a\x7fb"))))

    def test_header_name_must_be_an_rfc7230_token(self):
        for bad in ("X(", "X@Y", "Xé", "X\x7f"):
            with self.subTest(bad):
                errs = self._errs(lambda d, bad=bad: d["webhook"].update(headers=[{"key": bad, "value": "v"}]))
                self.assertTrue(any("headers[0].key" in e for e in errs), errs)
        self.assertEqual(self._errs(lambda d: d["webhook"].update(headers=[{"key": "X-Api_Key.1", "value": "v"}])), [])

    def test_header_value_must_be_a_string_and_present(self):
        for bad in ({"key": "X-A", "value": 5}, {"key": "X-A"}):
            with self.subTest(bad):
                errs = self._errs(lambda d, bad=bad: d["webhook"].update(headers=[bad]))
                self.assertTrue(any("headers[0].value" in e for e in errs), errs)

    def test_empty_notify_on_is_rejected_but_absent_is_fine(self):
        self.assertTrue(any("notify_on" in e for e in self._errs(lambda d: d.update(notify_on=[]))))
        self.assertEqual(validate_request(_valid()), [])

    def test_connector_id_must_be_a_positive_integer(self):
        for bad in (-5, 0, True, 1.5, {}, [1]):
            with self.subTest(bad):
                errs = self._errs(lambda d, bad=bad: d["connector"].update(id=bad))
                self.assertTrue(any("connector.id" in e for e in errs), errs)
        self.assertEqual(self._errs(lambda d: d["connector"].update(id=123)), [])
        self.assertEqual(self._errs(lambda d: d["connector"].update(id=None)), [])

    def test_non_string_scalars_are_errors_not_crashes(self):
        for mutate in (lambda d: d["connector"].update(name=5),
                       lambda d: d["webhook"].update(url=5),
                       lambda d: d["webhook"].update(auth={"type": "BASIC", "username": 1, "password": "p"}),
                       lambda d: d["webhook"].update(auth={"type": 5})):
            with self.subTest():
                self.assertIsInstance(self._errs(mutate), list)
                self.assertTrue(self._errs(mutate))


if __name__ == "__main__":
    unittest.main()
