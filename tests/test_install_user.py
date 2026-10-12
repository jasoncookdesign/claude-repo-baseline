import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import install_user as iu

TEMPLATE = {
    "permissions": {"deny": ["Bash(git push * main)", "Bash(gh api *merge*)"]},
    "hooks": {"PreToolUse": [{"matcher": "Bash|mcp__github__merge_pull_request",
                              "hooks": [{"type": "command", "command": "python3 {HOOKS_DIR}/guard.py"}]}]},
}


class MergeTests(unittest.TestCase):
    def test_into_empty(self):
        out = iu.merge_settings({}, TEMPLATE, "/h")
        self.assertEqual(out["permissions"]["deny"], TEMPLATE["permissions"]["deny"])
        self.assertEqual(out["hooks"]["PreToolUse"][0]["hooks"][0]["command"], "python3 /h/guard.py")

    def test_preserves_existing_keys_and_rules(self):
        existing = {"model": "x", "permissions": {"deny": ["Bash(rm -rf *)"], "allow": ["Read"]}}
        out = iu.merge_settings(existing, TEMPLATE, "/h")
        self.assertEqual(out["model"], "x")
        self.assertEqual(out["permissions"]["allow"], ["Read"])
        self.assertEqual(out["permissions"]["deny"][0], "Bash(rm -rf *)")
        self.assertIn("Bash(git push * main)", out["permissions"]["deny"])

    def test_idempotent(self):
        once = iu.merge_settings({}, TEMPLATE, "/h")
        twice = iu.merge_settings(once, TEMPLATE, "/h")
        self.assertEqual(once, twice)

    def test_does_not_mutate_inputs(self):
        existing = {"permissions": {"deny": ["a"]}}
        iu.merge_settings(existing, TEMPLATE, "/h")
        self.assertEqual(existing, {"permissions": {"deny": ["a"]}})

    def test_claude_md_block_replaced_not_duplicated(self):
        a = iu.merge_claude_md("# mine\n", "RULES")
        b = iu.merge_claude_md(a, "RULES v2")
        self.assertIn("# mine", b)
        self.assertEqual(b.count("BEGIN claude-repo-baseline"), 1)
        self.assertIn("RULES v2", b)
        self.assertNotIn("RULES\n", b.replace("RULES v2", ""))


class ShippedTemplateTests(unittest.TestCase):
    """The real user/settings.json, as the installer merges it."""

    def setUp(self):
        import json
        import pathlib
        self.root = pathlib.Path(iu.HERE)
        self.tpl = json.loads((self.root / "user" / "settings.json").read_text())
        self.out = iu.merge_settings({}, self.tpl, "/h/.claude/hooks")

    def entry(self, matcher):
        return next(e for e in self.out["hooks"]["PreToolUse"] if e["matcher"] == matcher)

    def test_merge_guard_command_unchanged(self):
        e = self.entry("Bash|mcp__github__merge_pull_request|mcp__github__enable_pr_auto_merge")
        self.assertEqual(e["hooks"][0]["command"], "python3 /h/.claude/hooks/guard_merge.py")

    def test_higgsfield_gate_wired_and_fails_closed(self):
        e = self.entry("mcp__claude_ai_Higgsfield__.*")
        self.assertEqual(e["hooks"], [{"type": "command", "command": "python3 /h/.claude/hooks/higgsfield_gate.py",
                                       "onFailure": "block"}])

    def test_reinstall_over_previous_install_adds_only_the_new_hook(self):
        previous = {"hooks": {"PreToolUse": [{
            "matcher": "Bash|mcp__github__merge_pull_request|mcp__github__enable_pr_auto_merge",
            "hooks": [{"type": "command", "command": "python3 /h/.claude/hooks/guard_merge.py"}]}]}}
        out = iu.merge_settings(previous, self.tpl, "/h/.claude/hooks")
        self.assertEqual(len(out["hooks"]["PreToolUse"]), 2)
        self.assertEqual(iu.merge_settings(out, self.tpl, "/h/.claude/hooks"), out)

    def test_every_referenced_hook_is_installed(self):
        import pathlib
        names = {pathlib.Path(h["command"].split()[-1]).name
                 for e in self.out["hooks"]["PreToolUse"] for h in e["hooks"]}
        installed = {dst.name for _, dst in iu.hook_targets(self.root / "hooks", pathlib.Path("/h/.claude/hooks"))}
        self.assertEqual(names, {"guard_merge.py", "higgsfield_gate.py"})
        self.assertLessEqual(names, installed)
        self.assertEqual(installed, {"guard_merge.py", "higgsfield_gate.py"})


class SkillTests(unittest.TestCase):
    def test_skill_targets(self):
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as t:
            src = pathlib.Path(t) / "skills"
            (src / "onboard-repo").mkdir(parents=True)
            (src / "onboard-repo" / "SKILL.md").write_text("x")
            (src / "stray.txt").write_text("y")
            out = iu.skill_targets(src, pathlib.Path("/h/.claude/skills"))
            self.assertEqual(out, [(src / "onboard-repo" / "SKILL.md",
                                    pathlib.Path("/h/.claude/skills/onboard-repo/SKILL.md"))])

    def test_missing_skills_dir(self):
        import pathlib
        self.assertEqual(iu.skill_targets(pathlib.Path("/nope"), pathlib.Path("/h")), [])


if __name__ == "__main__":
    unittest.main()
