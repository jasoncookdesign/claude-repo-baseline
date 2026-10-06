import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hooks"))
import guard_merge as g


def runner_returning(files, code=0):
    calls = []

    def run(argv):
        calls.append(argv)
        return code, "\n".join(files)

    run.calls = calls
    return run


class ParseTests(unittest.TestCase):
    def test_plain_merge_with_number(self):
        self.assertEqual(g.find_merges("gh pr merge 12 --squash"),
                         [{"selector": "12", "repo": None}])

    def test_no_selector(self):
        self.assertEqual(g.find_merges("gh pr merge --squash"),
                         [{"selector": None, "repo": None}])

    def test_repo_flag_forms(self):
        self.assertEqual(g.find_merges("gh pr merge -R a/b 3"),
                         [{"selector": "3", "repo": "a/b"}])
        self.assertEqual(g.find_merges("gh pr merge --repo=a/b 3"),
                         [{"selector": "3", "repo": "a/b"}])

    def test_value_flag_not_taken_as_selector(self):
        self.assertEqual(g.find_merges("gh pr merge --subject 'x y' 9"),
                         [{"selector": "9", "repo": None}])

    def test_compound_and_env_prefix(self):
        found = g.find_merges("cd x && GH_TOKEN=t gh pr merge 4; echo done")
        self.assertEqual(found, [{"selector": "4", "repo": None}])

    def test_bash_c_recursion(self):
        self.assertEqual(g.find_merges("bash -c 'gh pr merge 7'"),
                         [{"selector": "7", "repo": None}])

    def test_phrase_in_argument_is_not_a_merge(self):
        self.assertEqual(g.find_merges('git commit -m "docs: gh pr merge flow"'), [])

    def test_unrelated_commands(self):
        self.assertEqual(g.find_merges("gh pr view 3 && git status"), [])


class DecideTests(unittest.TestCase):
    def bash(self, cmd, run):
        return g.decide("Bash", {"command": cmd}, run)

    def test_allows_site_only_changes(self):
        ok, _ = self.bash("gh pr merge 5", runner_returning(["index.html", "blog/x.html"]))
        self.assertTrue(ok)

    def test_blocks_claude_dir(self):
        ok, why = self.bash("gh pr merge 5", runner_returning(["a.html", ".claude/settings.json"]))
        self.assertFalse(ok)
        self.assertIn(".claude/settings.json", why)

    def test_blocks_github_dir(self):
        ok, _ = self.bash("gh pr merge 5", runner_returning([".github/workflows/x.yml"]))
        self.assertFalse(ok)

    def test_does_not_block_lookalike_prefix(self):
        ok, _ = self.bash("gh pr merge 5", runner_returning(["docs/.github/x", ".claudex/y"]))
        self.assertTrue(ok)

    def test_fails_closed_when_gh_fails(self):
        ok, why = self.bash("gh pr merge 5", runner_returning([], code=1))
        self.assertFalse(ok)
        self.assertIn("could not", why.lower())

    def test_non_merge_command_allowed_without_calls(self):
        run = runner_returning([".claude/x"])
        ok, _ = self.bash("ls -la", run)
        self.assertTrue(ok)
        self.assertEqual(run.calls, [])

    def test_runner_gets_selector_and_repo(self):
        run = runner_returning(["a.html"])
        self.bash("gh pr merge -R o/r 8", run)
        self.assertEqual(run.calls[0], ["gh", "pr", "diff", "8", "--name-only", "-R", "o/r"])

    def test_mcp_merge_checked(self):
        run = runner_returning([".github/workflows/x.yml"])
        ok, _ = g.decide("mcp__github__merge_pull_request",
                         {"owner": "o", "repo": "r", "pullNumber": 8}, run)
        self.assertFalse(ok)
        self.assertEqual(run.calls[0], ["gh", "pr", "diff", "8", "--name-only", "-R", "o/r"])

    def test_mcp_auto_merge_checked(self):
        ok, _ = g.decide("mcp__github__enable_pr_auto_merge",
                         {"owner": "o", "repo": "r", "pullNumber": 8},
                         runner_returning([".claude/a"]))
        self.assertFalse(ok)

    def test_mcp_missing_fields_fails_closed(self):
        ok, _ = g.decide("mcp__github__merge_pull_request", {}, runner_returning([]))
        self.assertFalse(ok)

    def test_other_tools_allowed(self):
        ok, _ = g.decide("Read", {"file_path": "x"}, runner_returning([]))
        self.assertTrue(ok)


class MainTests(unittest.TestCase):
    def test_exit_codes(self):
        allow = g.main_with(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
                            runner_returning([]))
        block = g.main_with(json.dumps({"tool_name": "Bash",
                                        "tool_input": {"command": "gh pr merge 1"}}),
                            runner_returning([".claude/x"]))
        self.assertEqual(allow[0], 0)
        self.assertEqual(block[0], 2)
        self.assertIn(".claude/x", block[1])

    def test_bad_json_fails_closed(self):
        self.assertEqual(g.main_with("not json", runner_returning([]))[0], 2)


if __name__ == "__main__":
    unittest.main()
