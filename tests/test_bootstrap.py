import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bootstrap as b
import disciplines as d


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
            b._onboard_files("o/r", "standard", BLOCK)
        flat = [" ".join(c) for c in calls]
        commit = next(i for i, c in enumerate(flat) if c.startswith("git commit"))
        email = next(i for i, c in enumerate(flat) if c == "git config user.email github@jasoncookdesign.com")
        name = next(i for i, c in enumerate(flat) if c == "git config user.name Jason Cook")
        self.assertLess(email, commit)
        self.assertLess(name, commit)


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


class FakeClone:
    """Stands in for subprocess.run: seeds the clone dir and records commands and staged CLAUDE.md text."""

    def __init__(self, claude_md=None, open_pr_heads=()):
        self.claude_md, self.calls, self.staged = claude_md, [], {}
        self.open_pr_heads = list(open_pr_heads)

    def __call__(self, argv, **kw):
        argv = list(argv)
        self.calls.append(" ".join(argv))
        if argv[:3] == ["gh", "repo", "clone"] and self.claude_md is not None:
            with open(os.path.join(argv[4], "CLAUDE.md"), "w", newline="") as f:
                f.write(self.claude_md)
        if argv[:2] == ["git", "add"] and argv[2] == "CLAUDE.md":
            with open(os.path.join(kw["cwd"], "CLAUDE.md"), newline="") as f:
                self.staged["CLAUDE.md"] = f.read()
        if argv[:3] == ["gh", "pr", "list"]:
            head = argv[argv.index("--head") + 1]
            return mock.Mock(returncode=0, stdout="1\n" if head in self.open_pr_heads else "")
        return mock.Mock(returncode=0, stdout="")


BLOCK = d.render_block([("disciplines/t.md", "# T\n\nTOKEN-BLOCK-c0de\n")], "a" * 40)


class DisciplinesBlockTests(unittest.TestCase):
    def test_new_claude_md_gets_template_and_block(self):
        fake = FakeClone()
        with mock.patch.object(b.subprocess, "run", side_effect=fake):
            b._onboard_files("o/r", "scratch", BLOCK)
        text = fake.staged["CLAUDE.md"]
        self.assertTrue(text.startswith("# REPO_NAME"))
        self.assertIn("TOKEN-BLOCK-c0de", text)

    def test_existing_claude_md_is_kept_and_gets_block(self):
        fake = FakeClone(claude_md="@AGENTS.md\n")
        with mock.patch.object(b.subprocess, "run", side_effect=fake):
            b._onboard_files("o/r", "scratch", BLOCK)
        text = fake.staged["CLAUDE.md"]
        self.assertTrue(text.startswith("@AGENTS.md\n"))
        self.assertIn("TOKEN-BLOCK-c0de", text)
        self.assertNotIn("REPO_NAME", text)

    def test_refresh_opens_pr_on_its_own_branch_when_block_changes(self):
        fake = FakeClone(claude_md="# repo\n")
        with mock.patch.object(b.subprocess, "run", side_effect=fake):
            changed = b.refresh_disciplines("o/r", BLOCK)
        self.assertTrue(changed)
        self.assertIn("TOKEN-BLOCK-c0de", fake.staged["CLAUDE.md"])
        self.assertIn("git checkout -b chore/agentic-sdlc-disciplines-aaaaaaa", fake.calls)
        commit = next(i for i, c in enumerate(fake.calls) if c.startswith("git commit"))
        email = fake.calls.index("git config user.email github@jasoncookdesign.com")
        self.assertLess(email, commit)
        self.assertTrue(any(c.startswith("gh pr create") for c in fake.calls))

    def test_onboarding_with_nothing_to_change_does_not_commit(self):
        fake = FakeClone(claude_md=d.upsert_block("# repo\n", BLOCK))
        with mock.patch.object(b.subprocess, "run", side_effect=fake), quiet():
            b._onboard_files("o/r", "scratch", BLOCK)
        self.assertFalse([c for c in fake.calls if c.startswith(("git commit", "git push", "gh pr create"))])

    def test_refresh_branch_is_named_for_the_source_commit(self):
        fake = FakeClone(claude_md="# repo\n")
        with mock.patch.object(b.subprocess, "run", side_effect=fake), quiet():
            b.refresh_disciplines("o/r", BLOCK)
        self.assertIn("git checkout -b chore/agentic-sdlc-disciplines-aaaaaaa", fake.calls)

    def test_refresh_skips_when_its_pr_is_already_open(self):
        fake = FakeClone(claude_md="# repo\n", open_pr_heads=["chore/agentic-sdlc-disciplines-aaaaaaa"])
        with mock.patch.object(b.subprocess, "run", side_effect=fake), quiet():
            changed = b.refresh_disciplines("o/r", BLOCK)
        self.assertFalse(changed)
        self.assertFalse([c for c in fake.calls if c.startswith(("gh repo clone", "git push", "gh pr create"))])

    def test_refresh_does_not_create_a_missing_claude_md(self):
        fake = FakeClone()
        with mock.patch.object(b.subprocess, "run", side_effect=fake), quiet():
            changed = b.refresh_disciplines("o/r", BLOCK)
        self.assertFalse(changed)
        self.assertFalse([c for c in fake.calls if c.startswith(("git add", "git commit", "gh pr create"))])

    def test_crlf_claude_md_keeps_its_line_endings(self):
        fake = FakeClone(claude_md="# repo\r\n\r\nNotes.\r\n")
        with mock.patch.object(b.subprocess, "run", side_effect=fake), quiet():
            b.refresh_disciplines("o/r", BLOCK)
        staged = fake.staged["CLAUDE.md"]
        self.assertTrue(staged.startswith("# repo\r\n\r\nNotes.\r\n"))
        self.assertNotIn("\n", staged.replace("\r\n", ""))

    def test_disciplines_mode_validates_repo(self):
        with mock.patch.object(b.disciplines, "fetch_sources") as fetch:
            with self.assertRaises(ValueError):
                b.main(["no-slash", "--disciplines"])
        fetch.assert_not_called()

    def test_refresh_is_a_no_op_when_block_is_current(self):
        fake = FakeClone(claude_md=d.upsert_block("# repo\n", BLOCK))
        with mock.patch.object(b.subprocess, "run", side_effect=fake):
            with quiet():
                changed = b.refresh_disciplines("o/r", BLOCK)
        self.assertFalse(changed)
        self.assertFalse([c for c in fake.calls if c.startswith(("git commit", "git push", "gh pr create"))])

    def test_disciplines_mode_does_not_need_a_tier(self):
        with mock.patch.object(b, "refresh_disciplines", return_value=False) as refresh, \
             mock.patch.object(b.disciplines, "fetch_sources", return_value=([("disciplines/t.md", "# T\n")], "b" * 40)):
            with quiet():
                self.assertEqual(b.main(["o/r", "--disciplines", "--apply"]), 0)
        self.assertEqual(refresh.call_args.args[0], "o/r")
        self.assertIn("@bbbbbbb", refresh.call_args.args[1])

    def test_disciplines_mode_dry_run_changes_nothing(self):
        with mock.patch.object(b, "refresh_disciplines") as refresh, \
             mock.patch.object(b.disciplines, "fetch_sources", return_value=([("disciplines/t.md", "# T\n")], "b" * 40)):
            with quiet():
                self.assertEqual(b.main(["o/r", "--disciplines"]), 0)
        refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
