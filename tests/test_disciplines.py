import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import disciplines as d

# Fixture texts carry unique tokens so only real rendering can satisfy the assertions.
SOURCES = [
    ("disciplines/test-driven-development.md",
     "# Test-driven development\n\n## Iron law\n\n> TOKEN-TDD-7f3a\n\nBody one.\n"),
    ("disciplines/simplicity.md",
     "# Simplicity Fixture H44\n\n## Ladder Fixture H45\n\n> TOKEN-SIMPLE-91c2\n"),
]
SHA = "0123456789abcdef0123456789abcdef01234567"


class RenderBlockTests(unittest.TestCase):
    def test_block_is_delimited_and_pins_the_source_commit(self):
        block = d.render_block(SOURCES, SHA)
        lines = block.splitlines()
        self.assertTrue(lines[0].startswith(d.BEGIN))
        self.assertIn(SHA[:7], lines[0])
        self.assertEqual(lines[-1], d.END)

    def test_block_carries_every_source_in_order(self):
        block = d.render_block(SOURCES, SHA)
        self.assertLess(block.index("TOKEN-TDD-7f3a"), block.index("TOKEN-SIMPLE-91c2"))
        self.assertIn("Body one.", block)

    def test_headings_nest_under_one_section(self):
        block = d.render_block(SOURCES, SHA)
        self.assertIn("\n### Test-driven development\n", block)
        self.assertIn("\n#### Iron law\n", block)
        self.assertIn("\n### Simplicity Fixture H44\n", block)
        self.assertIn("\n#### Ladder Fixture H45\n", block)
        self.assertNotIn("\n# Test-driven development", block)
        self.assertNotIn("\n## Iron law", block)

    def test_block_states_the_skip_rule_and_lifecycle_link(self):
        block = d.render_block(SOURCES, SHA)
        self.assertIn("stated rationale", block)
        self.assertIn("https://github.com/jasoncookdesign/agentic-sdlc/blob/" + SHA + "/docs/lifecycle.md", block)

    def test_empty_sources_rejected(self):
        with self.assertRaises(ValueError):
            d.render_block([], SHA)


class UpsertBlockTests(unittest.TestCase):
    def setUp(self):
        self.block = d.render_block(SOURCES, SHA)

    def test_appends_when_absent_and_keeps_existing_text(self):
        out = d.upsert_block("# my-repo\n\nNotes.\n", self.block)
        self.assertTrue(out.startswith("# my-repo\n\nNotes.\n\n"))
        self.assertTrue(out.endswith(self.block + "\n"))

    def test_empty_file_gets_just_the_block(self):
        self.assertEqual(d.upsert_block("", self.block), self.block + "\n")

    def test_replaces_in_place_and_preserves_surroundings(self):
        old = d.render_block([("disciplines/x.md", "# Old\n\nTOKEN-OLD-55aa\n")], "f" * 40)
        text = "# repo\n\n" + old + "\n\n## After\n\nTail.\n"
        out = d.upsert_block(text, self.block)
        self.assertNotIn("TOKEN-OLD-55aa", out)
        self.assertIn("TOKEN-TDD-7f3a", out)
        self.assertTrue(out.startswith("# repo\n\n"))
        self.assertTrue(out.endswith("\n\n## After\n\nTail.\n"))
        self.assertEqual(out.count(d.BEGIN), 1)

    def test_idempotent(self):
        once = d.upsert_block("# r\n", self.block)
        self.assertEqual(d.upsert_block(once, self.block), once)

    def test_unterminated_block_is_an_error(self):
        with self.assertRaises(d.MalformedBlockError):
            d.upsert_block("x\n" + d.BEGIN + " @abc1234 -->\nstuff\n", self.block)


class FetchSourcesTests(unittest.TestCase):
    def test_fetches_each_path_at_one_pinned_commit(self):
        seen = []

        def fake_run(argv, **kw):
            seen.append(argv)
            out = SHA if argv[-1].endswith("commits/main") or "commits/main" in " ".join(argv) else "# T\n"
            return mock.Mock(stdout=out, returncode=0)

        with mock.patch.object(d.subprocess, "run", side_effect=fake_run):
            sources, sha = d.fetch_sources()
        self.assertEqual(sha, SHA)
        self.assertEqual([p for p, _ in sources], list(d.SOURCE_PATHS))
        content_calls = [" ".join(a) for a in seen if "contents/" in " ".join(a)]
        self.assertEqual(len(content_calls), len(d.SOURCE_PATHS))
        for call in content_calls:
            self.assertIn("ref=" + SHA, call)


if __name__ == "__main__":
    unittest.main()
