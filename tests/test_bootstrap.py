import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bootstrap as b


class PlanTests(unittest.TestCase):
    def test_repo_settings_call(self):
        plan = b.repo_settings_calls("o/r", "live")
        patch = plan[0]
        self.assertEqual(patch["method"], "PATCH")
        self.assertEqual(patch["path"], "repos/o/r")
        self.assertIs(patch["fields"]["delete_branch_on_merge"], True)
        self.assertIs(patch["fields"]["allow_auto_merge"], False)

    def test_live_tier_protects_main(self):
        plan = b.repo_settings_calls("o/r", "live")
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
        self.assertIn(".github/workflows/delete-unmerged-pr-branch.yml", b.files_for_tier("live"))
        self.assertIn("CLAUDE.md", b.files_for_tier("live"))
        self.assertNotIn(".github/workflows/delete-unmerged-pr-branch.yml", b.files_for_tier("scratch"))

    def test_bad_inputs(self):
        with self.assertRaises(ValueError):
            b.repo_settings_calls("no-slash", "live")
        with self.assertRaises(ValueError):
            b.repo_settings_calls("o/r", "bogus")

    def test_gh_argv(self):
        argv = b.gh_argv({"method": "PATCH", "path": "repos/o/r", "fields": {"a": True}})
        self.assertEqual(argv[:4], ["gh", "api", "-X", "PATCH"])
        self.assertIn("repos/o/r", argv)
        self.assertIn("a=true", argv)


if __name__ == "__main__":
    unittest.main()
