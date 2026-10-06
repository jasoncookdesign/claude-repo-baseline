#!/usr/bin/env python3
"""PreToolUse hook: refuse to merge a PR that touches .claude/ or .github/.

Guards `gh pr merge` (Bash) and the GitHub MCP merge / auto-merge tools.
Fails closed: if the changed-file list cannot be read, the merge is refused.
Exit 0 = allow, exit 2 = block (stderr is shown to the model).

Limits: it only sees `gh pr merge` in command position (including inside
`bash -c`). Other routes (`gh api .../merge`) are blocked by deny rules in
user/settings.json, so this hook is the one sanctioned door.
"""
import json
import re
import shlex
import subprocess
import sys

PROTECTED_PREFIXES = (".claude/", ".github/")
MERGE_TOOLS = {"mcp__github__merge_pull_request", "mcp__github__enable_pr_auto_merge"}
VALUE_FLAGS = {"-R", "--repo", "-t", "--subject", "-b", "--body", "-F", "--body-file",
               "-A", "--author-email", "--match-head-commit"}
SEPARATORS = re.compile(r"&&|\|\||;|\||\n")
SHELLS = {"bash", "sh", "zsh"}


def _tokens(segment):
    try:
        toks = shlex.split(segment)
    except ValueError:
        return []
    while toks and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]):
        toks.pop(0)
    return toks


def find_merges(command):
    found = []
    for segment in SEPARATORS.split(command):
        toks = _tokens(segment)
        if not toks:
            continue
        if toks[0] in SHELLS and "-c" in toks[1:]:
            idx = toks.index("-c")
            if idx + 1 < len(toks):
                found.extend(find_merges(toks[idx + 1]))
            continue
        if toks[:3] != ["gh", "pr", "merge"]:
            continue
        selector, repo, i, rest = None, None, 0, toks[3:]
        while i < len(rest):
            t = rest[i]
            if t.startswith("--") and "=" in t:
                name, _, val = t.partition("=")
                if name in ("--repo",):
                    repo = val
            elif t in VALUE_FLAGS:
                if t in ("-R", "--repo") and i + 1 < len(rest):
                    repo = rest[i + 1]
                i += 1
            elif t.startswith("-"):
                pass
            elif selector is None:
                selector = t
            i += 1
        found.append({"selector": selector, "repo": repo})
    return found


def _default_runner(argv):
    p = subprocess.run(argv, capture_output=True, text=True)
    return p.returncode, p.stdout


def _changed_files(selector, repo, run):
    argv = ["gh", "pr", "diff"] + ([selector] if selector else []) + ["--name-only"]
    if repo:
        argv += ["-R", repo]
    code, out = run(argv)
    if code != 0:
        return None
    return [line.strip() for line in out.splitlines() if line.strip()]


def _check(selector, repo, run):
    files = _changed_files(selector, repo, run)
    if files is None:
        return False, "Could not read the PR's changed files, so the merge is refused. Merge it yourself."
    hits = [f for f in files if f.startswith(PROTECTED_PREFIXES)]
    if hits:
        return False, "PR touches protected paths (owner merges these): " + ", ".join(hits)
    return True, ""


def decide(tool_name, tool_input, run=_default_runner):
    if tool_name in MERGE_TOOLS:
        owner, repo, num = (tool_input.get(k) for k in ("owner", "repo", "pullNumber"))
        if not (owner and repo and num):
            return False, "Merge call is missing owner, repo or pullNumber, so it is refused."
        return _check(str(num), f"{owner}/{repo}", run)
    if tool_name == "Bash":
        for m in find_merges(tool_input.get("command", "")):
            ok, why = _check(m["selector"], m["repo"], run)
            if not ok:
                return ok, why
    return True, ""


def main_with(stdin_text, run=_default_runner):
    try:
        event = json.loads(stdin_text)
        ok, why = decide(event.get("tool_name", ""), event.get("tool_input") or {}, run)
    except Exception as exc:  # fail closed
        return 2, f"merge guard error, refusing: {exc}"
    return (0, "") if ok else (2, why)


if __name__ == "__main__":
    code, msg = main_with(sys.stdin.read())
    if msg:
        print(msg, file=sys.stderr)
    sys.exit(code)
