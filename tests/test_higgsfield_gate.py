"""Contract tests for hooks/higgsfield_gate.py, the PreToolUse gate on Higgsfield MCP tools.

Token contract (written by claude-skills `reels.py record RUN GEN-ID submitted`):
<gate dir>/<GEN-ID>.<random>.json holding {"version": 1, "gen_id", "run", "attempt", "created"},
with created in Unix seconds. Working files go under the git-ignored tests/.work/, never /tmp.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "higgsfield_gate.py"
WORK = ROOT / "tests" / ".work"
sys.path.insert(0, str(ROOT / "hooks"))
import higgsfield_gate as hg  # noqa: E402

P = "mcp__claude_ai_Higgsfield__"
NOW = 1_800_000_000.0


def event(tool, tool_input=None):
    return json.dumps({"session_id": "s", "hook_event_name": "PreToolUse", "tool_name": tool,
                       "tool_input": {} if tool_input is None else tool_input, "tool_use_id": "t"})


def single(prompt="sparse dark grid", **extra):
    return {"params": {"model": "seedance_2_5", "prompt": prompt, **extra}}


def batch(n):
    return {"requests": [{"index": i, "params": {"model": "seedance_2_5", "prompt": f"p{i}"}} for i in range(n)]}


class GateCase(unittest.TestCase):
    def setUp(self):
        WORK.mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(dir=WORK)
        self.addCleanup(tmp.cleanup)
        self.gate = Path(tmp.name) / "reels-gate"
        self.gate.mkdir(mode=0o700)

    def token(self, gen_id="GEN-01", age=10.0, name=None, body=None):
        data = {"version": 1, "gen_id": gen_id, "run": "/r/DH-REEL-0195-run.md", "attempt": 1,
                "created": NOW - age}
        p = self.gate / (name or f"{gen_id}.{os.urandom(4).hex()}.json")
        p.write_text(body if body is not None else json.dumps(data))
        return p

    def run_hook(self, stdin, now=NOW):
        return hg.main_with(stdin, gate_dir=self.gate, now=now)

    def assertDenied(self, result, *needles):
        code, out, err = result
        self.assertEqual(code, 2, (out, err))
        self.assertEqual(out, "")
        for n in needles:
            self.assertIn(n, err)

    def assertAllowed(self, result):
        self.assertEqual(result, (0, "", ""))

    def assertAsked(self, result, tool, *needles):
        code, out, err = result
        self.assertEqual(code, 0, err)
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(decision["hookEventName"], "PreToolUse")
        self.assertEqual(decision["permissionDecision"], "ask")
        self.assertIn(tool, decision["permissionDecisionReason"])
        self.assertIn("credits", decision["permissionDecisionReason"])
        for n in needles:
            self.assertIn(n, decision["permissionDecisionReason"])


class GenerateGateTests(GateCase):
    def test_asks_without_token(self):
        for tool in ("generate_video", "generate_image", "generate_audio"):
            self.assertAsked(self.run_hook(event(P + tool, single())), tool, "no gate token")

    def test_allowed_once_with_valid_token_which_is_consumed(self):
        t = self.token()
        self.assertAllowed(self.run_hook(event(P + "generate_video", single())))
        self.assertFalse(t.exists())
        self.assertAsked(self.run_hook(event(P + "generate_video", single())), "generate_video", "no gate token")

    def test_expired_token_asks_and_is_removed(self):
        t = self.token(age=hg.TOKEN_TTL_SECONDS + 1)
        self.assertAsked(self.run_hook(event(P + "generate_image", single())), "generate_image", "expired")
        self.assertFalse(t.exists())

    def test_token_just_inside_ttl_allowed(self):
        self.token(age=hg.TOKEN_TTL_SECONDS - 1)
        self.assertAllowed(self.run_hook(event(P + "generate_image", single())))

    def test_future_dated_token_asks(self):
        t = self.token(age=-120)
        self.assertAsked(self.run_hook(event(P + "generate_video", single())), "generate_video", "no gate token")
        self.assertTrue(t.exists())

    def test_malformed_tokens_never_count(self):
        bad = [
            self.token(name="GEN-01.a.json", body="not json"),
            self.token(name="GEN-01.b.json", body=json.dumps(["GEN-01"])),
            self.token(name="GEN-01.c.json", body=json.dumps({"version": 1, "gen_id": "REAL-01", "created": NOW})),
            self.token(name="GEN-01.d.json", body=json.dumps({"version": 1, "gen_id": "GEN-01", "created": "now"})),
            self.token(name="GEN-01.e.json", body=json.dumps({"version": 2, "gen_id": "GEN-01", "created": NOW})),
            self.token(name="GEN-01.f.json", body=json.dumps({"version": 1, "gen_id": "GEN-01", "created": True})),
            self.token(name="GEN-01.g.tmp", body=json.dumps({"version": 1, "gen_id": "GEN-01", "created": NOW})),
        ]
        self.assertAsked(self.run_hook(event(P + "generate_video", single())), "generate_video", "no gate token")
        self.assertTrue(all(p.exists() for p in bad))  # left alone, not consumed

    def test_one_token_per_call_oldest_first(self):
        old, new = self.token("GEN-01", age=60), self.token("GEN-03", age=5)
        self.assertAllowed(self.run_hook(event(P + "generate_video", single())))
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())

    def test_variants_need_one_token_each(self):
        a = self.token("GEN-01")
        self.assertAsked(self.run_hook(event(P + "generate_video", single(count=2))), "generate_video", "needs 2")
        self.assertTrue(a.exists())
        self.token("GEN-01")
        self.assertAllowed(self.run_hook(event(P + "generate_video", single(count=2))))
        self.assertEqual(list(self.gate.glob("*.json")), [])

    def test_odd_count_is_denied(self):
        self.token()
        for bad in (0, -1, 1.5, "2", True):
            self.assertDenied(self.run_hook(event(P + "generate_video", single(count=bad))))

    def test_single_call_without_params_needs_a_token(self):
        self.assertAsked(self.run_hook(event(P + "generate_video", {})), "generate_video", "no gate token")
        self.token()
        self.assertAllowed(self.run_hook(event(P + "generate_video", {})))

    def test_symlinked_token_does_not_count(self):
        real = self.token("GEN-01", name="elsewhere.txt")
        (self.gate / "GEN-01.a.json").symlink_to(real)
        (self.gate / "GEN-01.b.json").symlink_to(real)
        self.assertAsked(self.run_hook(event(P + "generate_video", single())), "generate_video", "no gate token")
        self.assertTrue(real.exists())

    def test_gate_dir_writable_by_others_denies(self):
        self.token()
        os.chmod(self.gate, 0o777)
        self.addCleanup(os.chmod, self.gate, 0o700)
        self.assertDenied(self.run_hook(event(P + "generate_video", single())), "0700")
        os.chmod(self.gate, 0o720)
        self.assertDenied(self.run_hook(event(P + "generate_video", single())), "0700")

    def test_batch_needs_one_token_per_request(self):
        a, b = self.token("GEN-01"), self.token("GEN-03")
        self.assertAsked(self.run_hook(event(P + "generate_video_batch", batch(3))), "generate_video_batch", "needs 3")
        self.assertTrue(a.exists() and b.exists())  # nothing consumed on a refusal
        self.assertAllowed(self.run_hook(event(P + "generate_video_batch", batch(2))))
        self.assertFalse(a.exists() or b.exists())

    def test_batch_without_a_request_list_denied(self):
        self.token()
        for bad in ({}, {"requests": []}, {"requests": "x"}):
            self.assertDenied(self.run_hook(event(P + "generate_image_batch", bad)))
        self.assertEqual(len(list(self.gate.glob("*.json"))), 1)

    def test_cost_preflight_needs_no_token(self):
        self.assertAllowed(self.run_hook(event(P + "generate_video", single(get_cost=True))))
        self.assertAllowed(self.run_hook(event(P + "generate_video",
                                               {"params": json.dumps(single(get_cost=True)["params"])})))

    def test_non_boolean_get_cost_is_spending(self):
        self.assertAsked(self.run_hook(event(P + "generate_video", single(get_cost="true"))), "generate_video",
                         "no gate token")
        self.assertAsked(self.run_hook(event(P + "generate_video", {"params": "not json"})), "generate_video",
                         "no gate token")

    def test_missing_gate_dir_asks(self):
        self.gate.rmdir()
        self.assertAsked(self.run_hook(event(P + "generate_video", single())), "generate_video", "no gate token")


class OtherToolTests(GateCase):
    def test_non_spending_tools_pass_untouched(self):
        t = self.token()
        for tool in ("balance", "transactions", "jobs_wait", "show_generation_by_ids", "models_explore",
                     "media_upload", "media_confirm", "list_projects", "get_preferences", "ads_studio_quote",
                     "ai_influencer_prepare", "create_project", "create_folder", "show_marketing_studio_v2"):
            self.assertAllowed(self.run_hook(event(P + tool, {"x": 1})))
        self.assertTrue(t.exists())

    def test_other_spending_tools_ask_jason(self):
        t = self.token()
        for tool in ("execute_preset", "motion_control", "reframe", "upscale_image", "upscale_video",
                     "outpaint_image", "remove_background", "generate_3d", "apps_invoke",
                     "ads_studio_generate", "ai_influencer_generate", "scene_builder_3d_generate_video",
                     "shorts_studio_create", "dubbing", "voice_change", "create_voice",
                     "scene_builder_3d_query_python", "scene_builder_3d_run_python", "update_preferences"):
            self.assertAsked(self.run_hook(event(P + tool, {"x": 1})), tool)
        self.assertTrue(t.exists())  # a Reel token never pays for something else

    def test_unknown_higgsfield_tool_asks(self):
        self.assertAsked(self.run_hook(event(P + "brand_new_tool", {})), "brand_new_tool")

    def test_tools_outside_higgsfield_pass(self):
        self.assertAllowed(self.run_hook(event("Bash", {"command": "ls"})))


class MalformedInputTests(GateCase):
    def test_malformed_stdin_denied(self):
        for raw in ("", "not json", "[]", json.dumps({"tool_input": {}}), json.dumps({"tool_name": 3}),
                    json.dumps({"tool_name": P + "generate_video", "tool_input": "x"})):
            self.assertDenied(self.run_hook(raw), "higgsfield gate")


class CommandLineTests(GateCase):
    """The installed entry point: real stdin, REELS_GATE_DIR, exit codes and streams."""

    def cli(self, stdin):
        env = dict(os.environ, REELS_GATE_DIR=str(self.gate))
        return subprocess.run([sys.executable, "-I", str(HOOK)], input=stdin, capture_output=True, text=True,
                              env=env)

    def test_end_to_end(self):
        p = self.gate / "GEN-02.abc.json"
        p.write_text(json.dumps({"version": 1, "gen_id": "GEN-02", "run": "/r.md", "attempt": 1,
                                 "created": time.time()}))
        r = self.cli(event(P + "generate_video", single()))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertFalse(p.exists())
        r = self.cli(event(P + "generate_video", single()))
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "ask")
        r = self.cli(event(P + "upscale_video", {}))
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertEqual(self.cli("garbage").returncode, 2)


if __name__ == "__main__":
    unittest.main()
