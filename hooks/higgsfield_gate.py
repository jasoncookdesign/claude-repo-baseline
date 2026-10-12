#!/usr/bin/env python3
"""PreToolUse hook: no Higgsfield credits are spent without a passed gate or Jason's say-so.

Installed with matcher `mcp__claude_ai_Higgsfield__.*` and onFailure "block".

- generate_image / generate_video / generate_audio and their _batch variants need one single-use
  gate token per request. claude-skills `/reels:assets` writes a token on
  `reels.py record RUN GEN-ID submitted`, which runs the same check as `check-submission` and
  counts the attempt. A token lives TOKEN_TTL_SECONDS and is deleted when used. No token: deny.
  A cost preflight (`get_cost: true` on a single call) spends nothing and passes.
- Read-only and free tools (READ_ONLY) pass untouched.
- Every other Higgsfield tool, including ones added later, may spend credits outside the Reel
  workflow, so it asks Jason in a permission prompt (auto mode can't approve it silently).
- Anything malformed or unreadable is denied (fail closed).

Token: $REELS_GATE_DIR (default ~/.local/state/reels-gate)/<GEN-ID>.<random>.json holding
{"version": 1, "gen_id": "GEN-NN", "run": PATH, "attempt": N, "created": UNIX_SECONDS}.
Exit 0 = allow (or JSON "ask" on stdout), exit 2 = deny (stderr is shown to Claude).
"""
import json
import os
import re
import sys
import time
from pathlib import Path

PREFIX = "mcp__claude_ai_Higgsfield__"
TOKEN_TTL_SECONDS = 15 * 60
CLOCK_SKEW_SECONDS = 60
GATED = {"generate_image", "generate_video", "generate_audio"}
GATED_BATCH = {f"{t}_batch" for t in GATED}
READ_ONLY = {
    "balance", "transactions", "show_plans_and_credits", "show_credit_reset",
    "jobs_wait", "job_display", "show_generation_by_ids", "show_generations", "show_result", "show_medias",
    "show_characters", "show_reference_elements", "show_katana_result", "show_marketing_studio_generations",
    "list_projects", "list_folders", "list_project_assets", "list_voices", "list_workspaces", "list_websites",
    "list_website_categories", "models_explore", "get_presets", "get_preset_instructions",
    "get_workflow_instructions", "get_workflow_bundle_file", "get_explainer_presets", "get_preferences",
    "resolve_explainer_preset", "apps_search", "apps_describe",
    "media_upload", "media_confirm", "media_import_url", "media_upload_widget",
    "ads_studio_quote", "ads_studio_get_brand", "ads_studio_get_product", "ads_studio_get_run",
    "ads_studio_list_brands", "ads_studio_list_products", "ads_studio_list_runs",
    "ai_influencer_get_options", "ai_influencer_get_settings", "ai_influencer_list_presets",
    "ai_influencer_prepare",
    "scene_builder_3d_get_artifact", "scene_builder_3d_get_blend", "scene_builder_3d_get_generation",
    "scene_builder_3d_get_glb", "scene_builder_3d_get_operation", "scene_builder_3d_get_project",
    "scene_builder_3d_list_generations", "scene_builder_3d_list_projects", "scene_builder_3d_search_assets",
    "scene_builder_3d_show_scene", "scene_builder_3d_query_python",
    "shorts_studio_list_presets", "shorts_studio_list_sessions", "shorts_studio_status",
    "video_analysis_jobs", "video_analysis_status",
    "tiktok_accounts", "tiktok_music_trending", "tiktok_publish_status", "website_status",
}
_GEN_ID_RE = re.compile(r"^GEN-\d+$")
HOW_TO = (f"Paid Higgsfield generations go through /reels:assets: run `reels.py check-submission RUN.md GEN-ID` "
          "then `reels.py record RUN.md GEN-ID submitted` for each request in this call, then call again "
          f"within {TOKEN_TTL_SECONDS // 60} minutes. Don't work around this; if the gate refuses, show Jason and stop.")


class Deny(Exception):
    pass


def default_gate_dir():
    return Path(os.environ.get("REELS_GATE_DIR") or Path.home() / ".local" / "state" / "reels-gate")


def _params(tool_input):
    params = tool_input.get("params")
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except ValueError:
            return None
    return params if isinstance(params, dict) else None


def _requests_needed(tool, tool_input):
    """Tokens this call needs: 0 for a cost preflight, 1 per request otherwise."""
    if tool in GATED_BATCH:
        reqs = tool_input.get("requests")
        if not isinstance(reqs, list) or not reqs:
            raise Deny(f"{tool}: can't count the requests in this batch, so it is refused. {HOW_TO}")
        return len(reqs)
    params = _params(tool_input)
    if params is not None and params.get("get_cost") is True:
        return 0
    return 1


def _read_token(path, now):
    """('valid' | 'expired', created), or None when the file isn't a token."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != 1:
        return None
    created, gen_id = data.get("created"), data.get("gen_id")
    if not isinstance(gen_id, str) or not _GEN_ID_RE.match(gen_id):
        return None
    if isinstance(created, bool) or not isinstance(created, (int, float)):
        return None
    age = now - created
    if age < -CLOCK_SKEW_SECONDS:
        return None
    return ("valid" if age <= TOKEN_TTL_SECONDS else "expired"), created


def _consume(gate_dir, needed, now, tool):
    try:
        paths = sorted(gate_dir.glob("GEN-*.json"))
    except OSError:
        paths = []
    valid, expired = [], 0
    for p in paths:
        state, created = _read_token(p, now) or (None, None)
        if state == "expired":
            expired += 1
            try:
                p.unlink()
            except OSError:
                pass
        elif state == "valid":
            valid.append((created, p.name, p))
    valid.sort()
    if len(valid) < needed:
        note = f" ({expired} expired token(s) removed)" if expired else ""
        raise Deny(f"{tool}: needs {needed} gate token(s), found {len(valid)}{note}. {HOW_TO}")
    used = 0
    for _, _, p in valid:
        if used == needed:
            break
        try:
            p.unlink()
            used += 1
        except FileNotFoundError:  # taken by a parallel call
            continue
    if used < needed:
        raise Deny(f"{tool}: gate tokens were taken by another call. {HOW_TO}")


def _ask(tool):
    reason = (f"Higgsfield {tool} may spend credits and isn't part of the gated Reel workflow. "
              "Allow only if Jason asked for this specific call.")
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                              "permissionDecisionReason": reason}})


def main_with(stdin_text, gate_dir=None, now=None):
    """Return (exit code, stdout, stderr)."""
    try:
        event = json.loads(stdin_text)
        if not isinstance(event, dict):
            raise Deny("hook input is not a JSON object")
        name, tool_input = event.get("tool_name"), event.get("tool_input")
        if not isinstance(name, str) or not isinstance(tool_input, dict):
            raise Deny("hook input lacks tool_name or tool_input")
        if not name.startswith(PREFIX):
            return 0, "", ""
        tool = name[len(PREFIX):]
        if tool in READ_ONLY:
            return 0, "", ""
        if tool not in GATED and tool not in GATED_BATCH:
            return 0, _ask(tool), ""
        needed = _requests_needed(tool, tool_input)
        if needed:
            _consume(gate_dir or default_gate_dir(), needed, time.time() if now is None else now, tool)
        return 0, "", ""
    except Deny as exc:
        return 2, "", f"higgsfield gate: {exc}"
    except Exception as exc:  # fail closed
        return 2, "", f"higgsfield gate error, refusing: {exc}"


if __name__ == "__main__":
    code, out, err = main_with(sys.stdin.read())
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    sys.exit(code)
