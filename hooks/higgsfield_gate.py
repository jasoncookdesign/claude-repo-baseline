#!/usr/bin/env python3
"""PreToolUse hook: no Higgsfield credits are spent without a passed gate or Jason's say-so.

Installed with matcher `mcp__claude_ai_Higgsfield__.*` and onFailure "block".

- generate_image / generate_video / generate_audio and their _batch variants need one single-use
  gate token per request. claude-skills `/reels:assets` writes a token on
  `reels.py record RUN GEN-ID submitted`, which runs the same check as `check-submission` and
  counts the attempt. A token lives TOKEN_TTL_SECONDS and is deleted when the hook allows the call
  (whether or not Higgsfield then submits a job). A call with count N needs N tokens. Too few tokens
  (none, expired, or a missing gate folder): no token is consumed and the call returns `ask`, a
  permission prompt for Jason. A token folder that isn't his, mode 0700, still denies.
- Open switch: while <gate dir>/open-until holds a Unix time in the future (at most 24 hours ahead),
  the gated generate calls and the creation tools in OPEN_COVERS pass without a token. Only Jason
  writes the file; it expires on its own. Publishing, deploy and unknown tools still ask.
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
    "manage_reference_elements", "media_upload", "media_confirm", "media_import_url", "media_upload_widget",
    "ads_studio_quote", "ads_studio_get_brand", "ads_studio_get_product", "ads_studio_get_run",
    "ads_studio_list_brands", "ads_studio_list_products", "ads_studio_list_runs",
    "ai_influencer_get_options", "ai_influencer_get_settings", "ai_influencer_list_presets",
    "ai_influencer_prepare", "create_project", "create_folder", "show_marketing_studio_v2",
    "scene_builder_3d_get_artifact", "scene_builder_3d_get_blend", "scene_builder_3d_get_generation",
    "scene_builder_3d_get_glb", "scene_builder_3d_get_operation", "scene_builder_3d_get_project",
    "scene_builder_3d_list_generations", "scene_builder_3d_list_projects", "scene_builder_3d_search_assets",
    "scene_builder_3d_show_scene",
    "shorts_studio_list_presets", "shorts_studio_list_sessions", "shorts_studio_status",
    "video_analysis_jobs", "video_analysis_status",
    "tiktok_accounts", "tiktok_music_trending", "tiktok_publish_status", "website_status",
}
OPEN_FILE = "open-until"
MAX_OPEN_SECONDS = 24 * 60 * 60
OPEN_COVERS = {
    "execute_preset", "motion_control", "reframe", "upscale_image", "upscale_video", "outpaint_image",
    "remove_background", "generate_3d", "apps_invoke", "ads_studio_generate", "ai_influencer_generate",
    "scene_builder_3d_generate_video", "scene_builder_3d_generate_angles", "shorts_studio_create", "dubbing",
    "voice_change", "create_voice", "create_voice_from_confirmed_audio",
}
_GEN_ID_RE = re.compile(r"^GEN-\d+$")
HOW_TO = (f"Paid Higgsfield generations go through /reels:assets: run `reels.py check-submission RUN.md GEN-ID` "
          "then `reels.py record RUN.md GEN-ID submitted` for each request in this call, then call again "
          f"within {TOKEN_TTL_SECONDS // 60} minutes. Don't work around this; if the gate refuses, show Jason and stop.")


class Deny(Exception):
    pass


class NoTokens(Exception):
    """Too few valid gate tokens: the call goes to Jason as a permission prompt."""


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
    """Tokens this call needs: 0 for a cost preflight, otherwise 1 per request and per variant."""
    if tool in GATED_BATCH:
        reqs = tool_input.get("requests")
        if not isinstance(reqs, list) or not reqs:
            raise Deny(f"{tool}: can't count the requests in this batch, so it is refused. {HOW_TO}")
        return len(reqs)
    params = _params(tool_input)
    if params is None:
        return 1
    if params.get("get_cost") is True:
        return 0
    count = params.get("count", 1)
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise Deny(f"{tool}: can't read count {count!r}, so the call is refused. {HOW_TO}")
    return count


def _read_token(path, now):
    """('valid' | 'expired', created), or None when the file isn't a token."""
    if path.is_symlink() or not path.is_file():
        return None
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


def _check_dir(gate_dir, tool):
    try:
        st = gate_dir.stat()
    except OSError:
        raise NoTokens("no gate token") from None
    if st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise Deny(f"{tool}: {gate_dir} must be yours with mode 0700 before its tokens count. {HOW_TO}")


def _consume(gate_dir, needed, now, tool):
    _check_dir(gate_dir, tool)
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
        note = f", {expired} expired token(s) removed" if expired else ""
        found = f"needs {needed} gate token(s), found {len(valid)}" if valid else "no gate token"
        raise NoTokens(f"{found}{note}")
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


def _is_open(gate_dir, now):
    """True while Jason's open-until file names a time ahead of now, within MAX_OPEN_SECONDS."""
    p = gate_dir / OPEN_FILE
    try:
        if p.is_symlink() or not p.is_file():
            return False
        until = float(p.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return now < until <= now + MAX_OPEN_SECONDS


def _ask(tool, detail=""):
    reason = (f"Higgsfield {tool} may spend credits and isn't part of the gated Reel workflow"
              f"{f' ({detail})' if detail else ''}. Allow only if Jason asked for this specific call.")
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
        gate_dir = gate_dir or default_gate_dir()
        now = time.time() if now is None else now
        if tool not in GATED and tool not in GATED_BATCH:
            if tool in OPEN_COVERS:
                try:
                    _check_dir(gate_dir, tool)
                except (Deny, NoTokens):  # an unusable gate folder never opens anything
                    return 0, _ask(tool), ""
                if _is_open(gate_dir, now):
                    return 0, "", ""
            return 0, _ask(tool), ""
        needed = _requests_needed(tool, tool_input)
        if needed:
            try:
                _check_dir(gate_dir, tool)
            except NoTokens:
                return 0, _ask(tool, "no gate token"), ""
            if _is_open(gate_dir, now):
                return 0, "", ""
            _consume(gate_dir, needed, now, tool)
        return 0, "", ""
    except NoTokens as exc:
        return 0, _ask(tool, str(exc)), ""
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
