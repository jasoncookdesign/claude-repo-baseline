import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bootstrap as b


class PlanTests(unittest.TestCase):
    def test_repo_settings_call(self):
        plan = b.repo_settings_calls("o/r", "standard")
        patch = plan[0]
        self.assertEqual(patch["method"], "PATCH")
        self.assertEqual(patch["path"], "repos/o/r")
        self.assertIs(patch["fields"]["delete_branch_on_merge"], True)
        self.assertIs(patch["fields"]["allow_auto_merge"], False)

    def test_standard_tier_protects_main(self):
        plan = b.repo_settings_calls("o/r", "standard")
        prot = [c for c in plan if c["path"].endswith("/branches/main/protection")]
        self.assertEqual(len(prot), 1)
        body = prot[0]["body"]
        self.assertEqual(body["required_pull_request_reviews"]["required_approving_review_count"], 0)
        self.assertIs(body["enforce_admins"], True)
        self.assertIs(body["allow_force_pushes"], False)

    def test_scratch_tier_skips_protection(self):
        plan = b.repo_settings_calls("o/r", "scratch")
        self.assertFalse([c for c in plan if "protection" in c["path"]])

    def test_files_for_tier(self):
        self.assertIn(".github/workflows/delete-unmerged-pr-branch.yml", b.files_for_tier("standard"))
        self.assertIn("CLAUDE.md", b.files_for_tier("standard"))
        self.assertNotIn(".github/workflows/delete-unmerged-pr-branch.yml", b.files_for_tier("scratch"))

    def test_bad_inputs(self):
        with self.assertRaises(ValueError):
            b.repo_settings_calls("no-slash", "standard")
        with self.assertRaises(ValueError):
            b.repo_settings_calls("o/r", "bogus")

    def test_gh_argv(self):
        argv = b.gh_argv({"method": "PATCH", "path": "repos/o/r", "fields": {"a": True}})
        self.assertEqual(argv[:4], ["gh", "api", "-X", "PATCH"])
        self.assertIn("repos/o/r", argv)
        self.assertIn("a=true", argv)

    def test_old_tier_names_rejected(self):
        for old in ("live", "private"):
            with self.assertRaises(ValueError):
                b.repo_settings_calls("o/r", old)

    def test_describe_call_shows_body(self):
        plan = b.repo_settings_calls("o/r", "standard")
        text = b.describe_call(plan[1])
        self.assertIn("gh api -X PUT repos/o/r/branches/main/protection --input -", text)
        self.assertIn('"enforce_admins": true', text)
        self.assertIn('"required_approving_review_count": 0', text)

    def test_describe_call_without_body_is_one_line(self):
        plan = b.repo_settings_calls("o/r", "standard")
        self.assertEqual(b.describe_call(plan[0]).count("\n"), 0)


class IdentityTests(unittest.TestCase):
    def test_identity_is_jason_cook_with_correct_email(self):
        self.assertEqual(b.IDENTITY, ("Jason Cook", "github@jasoncookdesign.com"))

    def test_onboarding_pins_identity_in_clone_before_commit(self):
        calls = []
        with mock.patch.object(b.subprocess, "run", side_effect=lambda argv, **kw: calls.append(list(argv))):
            b._onboard_files("o/r", "standard")
        flat = [" ".join(c) for c in calls]
        commit = next(i for i, c in enumerate(flat) if c.startswith("git commit"))
        email = next(i for i, c in enumerate(flat) if c == "git config user.email github@jasoncookdesign.com")
        name = next(i for i, c in enumerate(flat) if c == "git config user.name Jason Cook")
        self.assertLess(email, commit)
        self.assertLess(name, commit)


if __name__ == "__main__":
    unittest.main()
