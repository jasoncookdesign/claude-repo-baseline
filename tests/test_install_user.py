import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import install_user as iu

TEMPLATE = {
    "permissions": {"deny": ["Bash(git push * main)", "Bash(gh api *merge*)"]},
    "hooks": {"PreToolUse": [{"matcher": "Bash|mcp__github__merge_pull_request",
                              "hooks": [{"type": "command", "command": "python3 {HOOK}"}]}]},
}


class MergeTests(unittest.TestCase):
    def test_into_empty(self):
        out = iu.merge_settings({}, TEMPLATE, "/h/guard.py")
        self.assertEqual(out["permissions"]["deny"], TEMPLATE["permissions"]["deny"])
        self.assertEqual(out["hooks"]["PreToolUse"][0]["hooks"][0]["command"], "python3 /h/guard.py")

    def test_preserves_existing_keys_and_rules(self):
        existing = {"model": "x", "permissions": {"deny": ["Bash(rm -rf *)"], "allow": ["Read"]}}
        out = iu.merge_settings(existing, TEMPLATE, "/h/guard.py")
        self.assertEqual(out["model"], "x")
        self.assertEqual(out["permissions"]["allow"], ["Read"])
        self.assertEqual(out["permissions"]["deny"][0], "Bash(rm -rf *)")
        self.assertIn("Bash(git push * main)", out["permissions"]["deny"])

    def test_idempotent(self):
        once = iu.merge_settings({}, TEMPLATE, "/h/guard.py")
        twice = iu.merge_settings(once, TEMPLATE, "/h/guard.py")
        self.assertEqual(once, twice)

    def test_does_not_mutate_inputs(self):
        existing = {"permissions": {"deny": ["a"]}}
        iu.merge_settings(existing, TEMPLATE, "/h/guard.py")
        self.assertEqual(existing, {"permissions": {"deny": ["a"]}})

    def test_claude_md_block_replaced_not_duplicated(self):
        a = iu.merge_claude_md("# mine\n", "RULES")
        b = iu.merge_claude_md(a, "RULES v2")
        self.assertIn("# mine", b)
        self.assertEqual(b.count("BEGIN claude-repo-baseline"), 1)
        self.assertIn("RULES v2", b)
        self.assertNotIn("RULES\n", b.replace("RULES v2", ""))


if __name__ == "__main__":
    unittest.main()
