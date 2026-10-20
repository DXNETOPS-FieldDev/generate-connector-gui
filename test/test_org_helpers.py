"""Tests for org hierarchy helpers: root_orgs, find_org_root, validate_same_hierarchy, resolve_orgs."""
import unittest

import generate_connector as gc
from fixtures import ORGS_MULTI_ROOT, ORGS_SINGLE, ORGS_ORG_ADMIN


class TestRootOrgs(unittest.TestCase):

    def test_single_org_is_its_own_root(self):
        roots = gc.root_orgs(ORGS_SINGLE)
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0]["id"], 18223)

    def test_org_admin_has_exactly_one_root(self):
        roots = gc.root_orgs(ORGS_ORG_ADMIN)
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0]["id"], 4160)

    def test_multi_root_has_multiple_roots(self):
        roots = gc.root_orgs(ORGS_MULTI_ROOT)
        root_ids = {o["id"] for o in roots}
        # These parentId=0 orgs are all roots
        self.assertIn(1,    root_ids)
        self.assertIn(4160, root_ids)
        self.assertIn(4166, root_ids)
        self.assertIn(4168, root_ids)
        self.assertIn(4170, root_ids)
        self.assertIn(4207, root_ids)

    def test_children_never_appear_as_roots(self):
        roots = gc.root_orgs(ORGS_MULTI_ROOT)
        root_ids = {o["id"] for o in roots}
        for child_id in [4211, 4212, 4213, 4222, 4275, 6230, 6298, 6324, 13581]:
            self.assertNotIn(child_id, root_ids, f"child {child_id} should not be a root")


class TestFindOrgRoot(unittest.TestCase):

    def _lookup(self, orgs):
        id_set = {o["id"] for o in orgs}
        org_by_id = {o["id"]: o for o in orgs}
        return org_by_id, id_set

    def test_root_org_returns_itself(self):
        org_by_id, id_set = self._lookup(ORGS_MULTI_ROOT)
        self.assertEqual(gc.find_org_root(4160, org_by_id, id_set), 4160)

    def test_direct_child_returns_parent(self):
        org_by_id, id_set = self._lookup(ORGS_MULTI_ROOT)
        self.assertEqual(gc.find_org_root(4275,  org_by_id, id_set), 4160)  # Corporate → Carousel
        self.assertEqual(gc.find_org_root(6324,  org_by_id, id_set), 4160)  # Marubeni → Carousel
        self.assertEqual(gc.find_org_root(13581, org_by_id, id_set), 4160)  # Customer Realm → Carousel
        self.assertEqual(gc.find_org_root(6230,  org_by_id, id_set), 4166)  # SaskTel ICT PS → SaskTel

    def test_grandchild_walks_to_root(self):
        orgs = list(ORGS_MULTI_ROOT) + [{"id": 99999, "parentId": 4275, "name": "Grandchild"}]
        org_by_id, id_set = self._lookup(orgs)
        self.assertEqual(gc.find_org_root(99999, org_by_id, id_set), 4160)

    def test_single_org_root_is_itself(self):
        org_by_id, id_set = self._lookup(ORGS_SINGLE)
        self.assertEqual(gc.find_org_root(18223, org_by_id, id_set), 18223)


class TestValidateSameHierarchy(unittest.TestCase):

    def test_empty_list_is_valid(self):
        ok, _ = gc.validate_same_hierarchy([], ORGS_MULTI_ROOT)
        self.assertTrue(ok)

    def test_single_org_always_valid(self):
        selected = [o for o in ORGS_MULTI_ROOT if o["id"] == 4160]
        ok, _ = gc.validate_same_hierarchy(selected, ORGS_MULTI_ROOT)
        self.assertTrue(ok)

    def test_parent_and_direct_child_valid(self):
        selected = [o for o in ORGS_MULTI_ROOT if o["id"] in {4160, 4275}]
        ok, _ = gc.validate_same_hierarchy(selected, ORGS_MULTI_ROOT)
        self.assertTrue(ok)

    def test_two_siblings_valid(self):
        selected = [o for o in ORGS_MULTI_ROOT if o["id"] in {4275, 6324}]
        ok, _ = gc.validate_same_hierarchy(selected, ORGS_MULTI_ROOT)
        self.assertTrue(ok)

    def test_all_carousel_orgs_valid(self):
        selected = [o for o in ORGS_MULTI_ROOT if o["id"] in {4160, 4275, 6324, 13581}]
        ok, _ = gc.validate_same_hierarchy(selected, ORGS_MULTI_ROOT)
        self.assertTrue(ok)

    def test_two_different_root_orgs_rejected(self):
        selected = [o for o in ORGS_MULTI_ROOT if o["id"] in {4160, 4166}]
        ok, msg = gc.validate_same_hierarchy(selected, ORGS_MULTI_ROOT)
        self.assertFalse(ok)
        self.assertIn("2", msg)

    def test_children_from_different_roots_rejected(self):
        selected = [o for o in ORGS_MULTI_ROOT if o["id"] in {4275, 6230}]  # Carousel child + SaskTel child
        ok, msg = gc.validate_same_hierarchy(selected, ORGS_MULTI_ROOT)
        self.assertFalse(ok)

    def test_parent_plus_child_from_another_hierarchy_rejected(self):
        selected = [o for o in ORGS_MULTI_ROOT if o["id"] in {4160, 4213}]  # Carousel + Columbia child
        ok, msg = gc.validate_same_hierarchy(selected, ORGS_MULTI_ROOT)
        self.assertFalse(ok)

    def test_error_message_names_both_roots(self):
        selected = [o for o in ORGS_MULTI_ROOT if o["id"] in {4160, 4166}]
        ok, msg = gc.validate_same_hierarchy(selected, ORGS_MULTI_ROOT)
        self.assertFalse(ok)
        self.assertIn("Carousel", msg)
        self.assertIn("SaskTel", msg)


class TestResolveOrgs(unittest.TestCase):

    def test_single_id_exact_match(self):
        matched, errors = gc.resolve_orgs(ORGS_MULTI_ROOT, [4160])
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["id"], 4160)
        self.assertEqual(errors, [])

    def test_multiple_ids(self):
        matched, errors = gc.resolve_orgs(ORGS_MULTI_ROOT, [4160, 4275])
        self.assertEqual({o["id"] for o in matched}, {4160, 4275})
        self.assertEqual(errors, [])

    def test_numeric_string_treated_as_id(self):
        matched, errors = gc.resolve_orgs(ORGS_MULTI_ROOT, ["4160"])
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["id"], 4160)

    def test_comma_split_ids(self):
        specs = [s.strip() for s in "4160,4275".split(",")]
        matched, errors = gc.resolve_orgs(ORGS_MULTI_ROOT, specs)
        self.assertEqual({o["id"] for o in matched}, {4160, 4275})
        self.assertEqual(errors, [])

    def test_name_substring_case_insensitive(self):
        matched, errors = gc.resolve_orgs(ORGS_MULTI_ROOT, ["carousel"])
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["id"], 4160)

    def test_name_substring_unique_match(self):
        # "Closter" uniquely matches "Closter BOE" (id=4207)
        matched, errors = gc.resolve_orgs(ORGS_MULTI_ROOT, ["Closter"])
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["id"], 4207)

    def test_ambiguous_name_returns_error(self):
        # "SaskTel" matches both "SaskTel" (4166) and "SaskTel ICT PS" (6230)
        matched, errors = gc.resolve_orgs(ORGS_MULTI_ROOT, ["SaskTel"])
        self.assertEqual(len(matched), 0)
        self.assertEqual(len(errors), 1)
        self.assertIn("ambiguous", errors[0].lower())

    def test_unknown_id_returns_error(self):
        matched, errors = gc.resolve_orgs(ORGS_MULTI_ROOT, [99999])
        self.assertEqual(matched, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("99999", errors[0])
        self.assertIn(str(len(ORGS_MULTI_ROOT)), errors[0])

    def test_unknown_name_returns_error(self):
        matched, errors = gc.resolve_orgs(ORGS_MULTI_ROOT, ["zzz_definitely_not_an_org"])
        self.assertEqual(matched, [])
        self.assertEqual(len(errors), 1)

    def test_duplicate_ids_collapsed(self):
        matched, errors = gc.resolve_orgs(ORGS_MULTI_ROOT, [4160, 4160])
        self.assertEqual(len(matched), 1)
        self.assertEqual(errors, [])

    def test_mixed_id_and_name(self):
        # "Closter" uniquely matches "Closter BOE" (4207)
        matched, errors = gc.resolve_orgs(ORGS_MULTI_ROOT, [4160, "Closter"])
        self.assertEqual({o["id"] for o in matched}, {4160, 4207})
        self.assertEqual(errors, [])

    def test_toml_list_of_ints(self):
        matched, errors = gc.resolve_orgs(ORGS_MULTI_ROOT, [4160, 4275])
        self.assertEqual({o["id"] for o in matched}, {4160, 4275})
        self.assertEqual(errors, [])

    def test_single_org_set_no_validation_needed(self):
        matched, errors = gc.resolve_orgs(ORGS_SINGLE, [18223])
        self.assertEqual(len(matched), 1)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
