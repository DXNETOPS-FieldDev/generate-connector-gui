"""Tests for _remove_contradictions, merge_with_existing, and diff_connector."""
import unittest

import generate_connector as gc


class TestRemoveContradictions(unittest.TestCase):

    def test_no_overlap_leaves_both_blocks_unchanged(self):
        inc = {"severity": ["CRITICAL"], "monitoringPointId": [100]}
        exc = {"severity": ["MINOR"],    "monitoringPointId": [200]}
        errors = []
        gc._remove_contradictions(inc, exc, errors, "TestOrg")
        self.assertEqual(inc["severity"], ["CRITICAL"])
        self.assertEqual(exc["severity"], ["MINOR"])
        self.assertEqual(errors, [])

    def test_severity_contradiction_removed_from_include_kept_in_exclude(self):
        inc = {"severity": ["CRITICAL", "MAJOR"]}
        exc = {"severity": ["MAJOR", "MINOR"]}
        errors = []
        gc._remove_contradictions(inc, exc, errors, "TestOrg")
        self.assertNotIn("MAJOR", inc["severity"])
        self.assertIn("MAJOR", exc["severity"])
        self.assertIn("CRITICAL", inc["severity"])
        self.assertIn("MINOR", exc["severity"])

    def test_contradiction_appends_error_record(self):
        inc = {"severity": ["CRITICAL", "MAJOR"]}
        exc = {"severity": ["MAJOR"]}
        errors = []
        gc._remove_contradictions(inc, exc, errors, "MyOrg")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["type"], "contradiction")
        self.assertEqual(errors[0]["org"], "MyOrg")

    def test_all_include_values_contradicted_removes_include_field_kept_in_exclude(self):
        inc = {"severity": ["CRITICAL"]}
        exc = {"severity": ["CRITICAL"]}
        errors = []
        gc._remove_contradictions(inc, exc, errors, "TestOrg")
        self.assertNotIn("severity", inc)
        self.assertEqual(exc["severity"], ["CRITICAL"])

    def test_mp_id_contradiction_removed(self):
        inc = {"monitoringPointId": [100, 101]}
        exc = {"monitoringPointId": [101, 102]}
        errors = []
        gc._remove_contradictions(inc, exc, errors, "TestOrg")
        self.assertNotIn(101, inc.get("monitoringPointId", []))
        self.assertIn(101, exc["monitoringPointId"])
        self.assertIn(100, inc["monitoringPointId"])
        self.assertIn(102, exc["monitoringPointId"])

    def test_policy_group_id_contradiction_removed(self):
        inc = {"monitoringPolicyGroupId": [10, 20]}
        exc = {"monitoringPolicyGroupId": [20, 30]}
        errors = []
        gc._remove_contradictions(inc, exc, errors, "TestOrg")
        self.assertNotIn(20, inc.get("monitoringPolicyGroupId", []))
        self.assertIn(20, exc["monitoringPolicyGroupId"])

    def test_tag_contradiction_equal_counts_removed_from_include_kept_in_exclude(self):
        inc = {"tag": [{"category": "Region", "value": "West"}]}
        exc = {"tag": [{"category": "Region", "value": "West"}]}
        errors = []
        gc._remove_contradictions(inc, exc, errors, "TestOrg")
        self.assertNotIn("tag", inc)
        self.assertEqual(exc["tag"], [{"category": "Region", "value": "West"}])
        self.assertEqual(len(errors), 1)

    def test_tag_partial_overlap_removed_from_larger_list_side_kept_in_exception_side(self):
        # include has 2 Region tags (the "list"), exclude has 1 (the "exception") --
        # the overlapping value is removed from the list side (include) and kept on
        # the exception side (exclude).
        inc = {"tag": [{"category": "Region", "value": "West"}, {"category": "Region", "value": "East"}]}
        exc = {"tag": [{"category": "Region", "value": "West"}]}
        errors = []
        gc._remove_contradictions(inc, exc, errors, "TestOrg")
        remaining_inc = inc.get("tag", [])
        self.assertEqual(len(remaining_inc), 1)
        self.assertEqual(remaining_inc[0]["value"], "East")
        self.assertEqual(exc["tag"], [{"category": "Region", "value": "West"}])

    def test_empty_blocks_do_not_raise(self):
        gc._remove_contradictions({}, {}, [], "TestOrg")

    def test_noise_filter_contradiction(self):
        inc = {"noiseFilter": ["FREQUENT"]}
        exc = {"noiseFilter": ["FREQUENT"]}
        errors = []
        gc._remove_contradictions(inc, exc, errors, "TestOrg")
        self.assertNotIn("noiseFilter", inc)
        self.assertEqual(exc["noiseFilter"], ["FREQUENT"])


class TestMergeWithExisting(unittest.TestCase):

    EXISTING = {
        "name": "Old Name",
        "enabled": True,
        "description": "Old description",
        "include": {
            "severity": ["CRITICAL"],
            "monitoringPointId": [100, 101],
        },
        "exclude": {
            "noiseFilter": ["FREQUENT"],
        },
        "notifyOn": ["ALARM_RAISED"],
        "connectors": [{"type": "WEBHOOK", "url": "https://old.example.com"}],
    }

    def test_payload_name_overrides_existing(self):
        merged = gc.merge_with_existing({"name": "New Name"}, self.EXISTING)
        self.assertEqual(merged["name"], "New Name")

    def test_payload_enabled_overrides_existing(self):
        merged = gc.merge_with_existing({"name": "X", "enabled": False}, self.EXISTING)
        self.assertEqual(merged["enabled"], False)

    def test_existing_description_preserved_when_absent_from_payload(self):
        merged = gc.merge_with_existing({"name": "X"}, self.EXISTING)
        self.assertEqual(merged["description"], "Old description")

    def test_payload_description_overrides_existing(self):
        merged = gc.merge_with_existing({"name": "X", "description": "New desc"}, self.EXISTING)
        self.assertEqual(merged["description"], "New desc")

    def test_include_block_merged(self):
        payload = {"name": "X", "include": {"severity": ["MAJOR"]}}
        merged = gc.merge_with_existing(payload, self.EXISTING)
        # payload severity overrides existing severity
        self.assertEqual(merged["include"]["severity"], ["MAJOR"])
        # existing monitoringPointId preserved since payload did not specify it
        self.assertEqual(merged["include"]["monitoringPointId"], [100, 101])

    def test_exclude_block_merged(self):
        payload = {"name": "X", "exclude": {"severity": ["MINOR"]}}
        merged = gc.merge_with_existing(payload, self.EXISTING)
        self.assertEqual(merged["exclude"]["severity"], ["MINOR"])
        # existing noiseFilter preserved
        self.assertEqual(merged["exclude"]["noiseFilter"], ["FREQUENT"])

    def test_payload_without_include_preserves_existing_include(self):
        payload = {"name": "X"}
        merged = gc.merge_with_existing(payload, self.EXISTING)
        self.assertEqual(merged["include"]["severity"], ["CRITICAL"])

    def test_original_payload_not_mutated(self):
        payload = {"name": "X", "include": {"severity": ["MAJOR"]}}
        original_payload = dict(payload)
        gc.merge_with_existing(payload, self.EXISTING)
        self.assertEqual(payload["name"], original_payload["name"])

    def test_subconnector_id_preserved_by_index(self):
        # AppNeta rejects a PUT whose connectors[n] entries are missing 'id'
        # -- merge must carry it over from the
        # existing connector, matched by list index.
        existing = {**self.EXISTING, "connectors": [{"id": 88001, "type": "WEBHOOK", "url": "https://old.example.com"}]}
        payload = {"name": "X", "connectors": [{"type": "WEBHOOK", "url": "https://new.example.com"}]}
        merged = gc.merge_with_existing(payload, existing)
        self.assertEqual(merged["connectors"][0]["id"], 88001)
        self.assertEqual(merged["connectors"][0]["url"], "https://new.example.com")

    def test_subconnector_explicit_id_in_payload_overrides_existing(self):
        existing = {**self.EXISTING, "connectors": [{"id": 88001, "type": "WEBHOOK", "url": "https://old.example.com"}]}
        payload = {"name": "X", "connectors": [{"id": 99999, "type": "WEBHOOK", "url": "https://new.example.com"}]}
        merged = gc.merge_with_existing(payload, existing)
        self.assertEqual(merged["connectors"][0]["id"], 99999)

    # ── regressions: UPDATE must be able to drop auth / headers / SSL bypass ──

    _OLD_SUB = {"id": 7, "type": "WEBHOOK", "url": "https://old.example.com",
                "auth": {"type": "BASIC", "username": "u", "password": "********"},
                "headers": [{"key": "X-Secret", "value": "********"}],
                "ignoreSSLErrors": True}

    def test_subconnector_carries_only_id_from_existing(self):
        existing = {**self.EXISTING, "connectors": [dict(self._OLD_SUB)]}
        payload = {"name": "X", "connectors": [{"type": "WEBHOOK", "url": "https://new.example.com"}]}
        sub = gc.merge_with_existing(payload, existing)["connectors"][0]
        self.assertEqual(sub["id"], 7)
        self.assertNotIn("auth", sub)
        self.assertNotIn("headers", sub)

    def test_ssl_verification_can_be_turned_back_on(self):
        existing = {**self.EXISTING, "connectors": [dict(self._OLD_SUB)]}
        payload = {"name": "X", "connectors": [{"type": "WEBHOOK", "url": "https://new.example.com"}]}
        sub = gc.merge_with_existing(payload, existing)["connectors"][0]
        self.assertIs(sub["ignoreSSLErrors"], False)

    def test_contradiction_created_by_merge_is_resolved_and_reported(self):
        # existing include has CRITICAL; the user now excludes CRITICAL
        payload = {"name": "X", "exclude": {"severity": ["CRITICAL"]}}
        errors = []
        merged = gc.merge_with_existing(payload, self.EXISTING, errors=errors, org_name="Acme")
        self.assertNotIn("severity", merged["include"])
        self.assertEqual(merged["exclude"]["severity"], ["CRITICAL"])
        self.assertTrue(any(e.get("type") == "contradiction" for e in errors))


class TestDiffConnector(unittest.TestCase):

    def test_identical_payloads_produce_no_diff(self):
        p = {"name": "Test", "enabled": True, "include": {"severity": ["CRITICAL"]}}
        self.assertEqual(gc.diff_connector(p, p), [])

    def test_name_change_detected(self):
        current  = {"name": "Old"}
        proposed = {"name": "New"}
        lines = gc.diff_connector(current, proposed)
        self.assertTrue(any("name" in l for l in lines))

    def test_enabled_change_detected(self):
        current  = {"name": "X", "enabled": True}
        proposed = {"name": "X", "enabled": False}
        lines = gc.diff_connector(current, proposed)
        self.assertTrue(any("enabled" in l for l in lines))

    def test_new_description_marked_as_added(self):
        current  = {"name": "X"}
        proposed = {"name": "X", "description": "New desc"}
        lines = gc.diff_connector(current, proposed)
        self.assertTrue(any("+" in l for l in lines))

    def test_removed_field_marked_as_removed(self):
        current  = {"name": "X", "description": "Old desc"}
        proposed = {"name": "X"}
        lines = gc.diff_connector(current, proposed)
        self.assertTrue(any("-" in l for l in lines))

    def test_severity_change_in_include_detected(self):
        current  = {"name": "X", "include": {"severity": ["CRITICAL"]}}
        proposed = {"name": "X", "include": {"severity": ["MAJOR"]}}
        lines = gc.diff_connector(current, proposed)
        self.assertTrue(any("severity" in l for l in lines))

    def test_no_diff_when_include_unchanged(self):
        p = {"name": "X", "include": {"severity": ["CRITICAL"]}, "notifyOn": ["ALARM_RAISED"]}
        self.assertEqual(gc.diff_connector(p, p), [])


if __name__ == "__main__":
    unittest.main()
