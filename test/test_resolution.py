"""Tests for pure name/ID resolution helpers and utility functions."""
import unittest

import generate_connector as gc
from fixtures import MONITORING_POINTS, POLICIES


class TestIsNumeric(unittest.TestCase):

    def test_integer_string(self):
        self.assertTrue(gc.is_numeric("12345"))

    def test_zero(self):
        self.assertTrue(gc.is_numeric("0"))

    def test_alpha_string(self):
        self.assertFalse(gc.is_numeric("abc"))

    def test_float_string(self):
        self.assertFalse(gc.is_numeric("1.5"))

    def test_empty_string(self):
        self.assertFalse(gc.is_numeric(""))

    def test_alphanumeric(self):
        self.assertFalse(gc.is_numeric("123abc"))


class TestHasGlob(unittest.TestCase):

    def test_star(self):
        self.assertTrue(gc._has_glob("ACME-*"))

    def test_double_star(self):
        self.assertTrue(gc._has_glob("ACME-**"))

    def test_question(self):
        self.assertTrue(gc._has_glob("ACME-?"))

    def test_bang(self):
        self.assertTrue(gc._has_glob("!exclude"))

    def test_plus(self):
        self.assertTrue(gc._has_glob("ACME-+"))

    def test_plain_name_no_glob(self):
        self.assertFalse(gc._has_glob("ACME-Lab-Rocket"))

    def test_empty_string(self):
        self.assertFalse(gc._has_glob(""))


class TestParseTagSpec(unittest.TestCase):

    def test_exact_pair(self):
        self.assertEqual(gc.parse_tag_spec("Location:Chicago IL"), ("Location", "Chicago IL"))

    def test_category_only(self):
        self.assertEqual(gc.parse_tag_spec("Location"), ("Location", None))

    def test_value_only(self):
        self.assertEqual(gc.parse_tag_spec(":Chicago IL"), (None, "Chicago IL"))

    def test_strips_surrounding_whitespace(self):
        cat, val = gc.parse_tag_spec("  Location : Chicago IL  ")
        self.assertEqual(cat, "Location")
        self.assertEqual(val, "Chicago IL")

    def test_colon_with_empty_value_returns_none_value(self):
        cat, val = gc.parse_tag_spec("Location:")
        self.assertEqual(cat, "Location")
        self.assertIsNone(val)

    def test_empty_string_returns_none_none(self):
        cat, val = gc.parse_tag_spec("")
        self.assertIsNone(cat)
        self.assertIsNone(val)


class TestResolveToIds(unittest.TestCase):

    def test_name_resolves_to_id(self):
        errors = []
        result = gc.resolve_to_ids(
            ["ACME-MP-MesaFlats"], MONITORING_POINTS, "name", "id", "MP", errors, "TestOrg"
        )
        self.assertEqual(result, [100])
        self.assertEqual(errors, [])

    def test_numeric_id_passthrough(self):
        errors = []
        result = gc.resolve_to_ids(
            ["101"], MONITORING_POINTS, "name", "id", "MP", errors, "TestOrg"
        )
        self.assertEqual(result, [101])
        self.assertEqual(errors, [])

    def test_name_match_is_case_insensitive(self):
        errors = []
        result = gc.resolve_to_ids(
            ["acme-mp-mesaflats"], MONITORING_POINTS, "name", "id", "MP", errors, "TestOrg"
        )
        self.assertEqual(result, [100])
        self.assertEqual(errors, [])

    def test_unknown_name_appends_error(self):
        errors = []
        gc.resolve_to_ids(
            ["ACME-MP-NonExistent"], MONITORING_POINTS, "name", "id", "MP", errors, "TestOrg"
        )
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["value"], "ACME-MP-NonExistent")
        self.assertEqual(errors[0]["org"], "TestOrg")

    def test_unknown_id_appends_error(self):
        errors = []
        gc.resolve_to_ids(
            ["99999"], MONITORING_POINTS, "name", "id", "MP", errors, "TestOrg"
        )
        self.assertEqual(len(errors), 1)

    def test_multiple_names_resolved(self):
        errors = []
        result = gc.resolve_to_ids(
            ["ACME-MP-MesaFlats", "ACME-MP-CanyonRoad"],
            MONITORING_POINTS, "name", "id", "MP", errors, "TestOrg"
        )
        self.assertEqual(sorted(result), [100, 101])
        self.assertEqual(errors, [])

    def test_mixed_names_and_ids(self):
        errors = []
        result = gc.resolve_to_ids(
            ["ACME-MP-MesaFlats", "101"],
            MONITORING_POINTS, "name", "id", "MP", errors, "TestOrg"
        )
        self.assertEqual(sorted(result), [100, 101])
        self.assertEqual(errors, [])

    def test_policy_name_resolves(self):
        errors = []
        result = gc.resolve_to_ids(
            ["Southwest Desert"], POLICIES, "name", "id", "policy", errors, "TestOrg"
        )
        self.assertEqual(result, [200])
        self.assertEqual(errors, [])


class TestResolveMpTypes(unittest.TestCase):

    def test_substring_match(self):
        errors = []
        result = gc.resolve_mp_types(["m50"], MONITORING_POINTS, errors, "TestOrg")
        self.assertIn("m50 microAppliance", result)

    def test_c50_substring_match(self):
        errors = []
        result = gc.resolve_mp_types(["c50"], MONITORING_POINTS, errors, "TestOrg")
        self.assertIn("c50 Container", result)

    def test_n10_alias_expands(self):
        errors = []
        result = gc.resolve_mp_types(["n10"], MONITORING_POINTS, errors, "TestOrg")
        self.assertIn("Windows", result)
        self.assertIn("macOS", result)

    def test_glob_passed_through(self):
        errors = []
        result = gc.resolve_mp_types(["m50*"], MONITORING_POINTS, errors, "TestOrg")
        self.assertIn("m50*", result)

    def test_unknown_type_appends_error(self):
        errors = []
        gc.resolve_mp_types(["bogusType"], MONITORING_POINTS, errors, "TestOrg")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["value"], "bogusType")

    def test_deduplication(self):
        errors = []
        result = gc.resolve_mp_types(["m50", "m50"], MONITORING_POINTS, errors, "TestOrg")
        self.assertEqual(result.count("m50 microAppliance"), 1)


if __name__ == "__main__":
    unittest.main()
