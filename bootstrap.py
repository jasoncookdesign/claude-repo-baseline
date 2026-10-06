#!/usr/bin/env python3
"""Onboard one repo: apply GitHub repo settings and open a PR with the baseline files.

Usage: python3 bootstrap.py OWNER/REPO --tier standard|scratch [--apply]
Default is a dry run that prints the plan. Needs `gh` authenticated locally.
Tiers: standard = protect main, add the cleanup workflow and CLAUDE.md;
scratch = settings and CLAUDE.md only, no protection and no workflow.
"""
import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

import disciplines

HERE = pathlib.Path(__file__).resolve().parent
TIERS = ("standard", "scratch")
WORKFLOW = ".github/workflows/delete-unmerged-pr-branch.yml"
IDENTITY = ("Jason Cook", "github@jasoncookdesign.com")  # pinned so the global git config cannot leak in


def _validate(repo, tier):
    if repo.count("/") != 1 or not all(repo.split("/")):
        raise ValueError(f"repo must be OWNER/REPO, got {repo!r}")
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}, got {tier!r}")


def repo_settings_calls(repo, tier):
    _validate(repo, tier)
    calls = [{"method": "PATCH", "path": f"repos/{repo}",
              "fields": {"delete_branch_on_merge": True, "allow_auto_merge": False}}]
    if tier == "standard":
        calls.append({"method": "PUT", "path": f"repos/{repo}/branches/main/protection",
                      "body": {"required_status_checks": None, "enforce_admins": True,
                               "required_pull_request_reviews": {"required_approving_review_count": 0},
                               "restrictions": None, "allow_force_pushes": False,
                               "allow_deletions": False}})
    return calls


def files_for_tier(tier):
    if tier == "scratch":
        return ["CLAUDE.md"]
    return ["CLAUDE.md", WORKFLOW]


def gh_argv(call):
    argv = ["gh", "api", "-X", call["method"], call["path"]]
    for key, val in call.get("fields", {}).items():
        argv += ["-F", f"{key}={json.dumps(val)}"]
    if "body" in call:
        argv += ["--input", "-"]
    return argv


def describe_call(call):
    """Printable form of a call, including the JSON body it will send."""
    line = " ".join(gh_argv(call))
    if "body" in call:
        line += "\n" + json.dumps(call["body"], indent=2)
    return line


def _clone_on_branch(repo, tmp, branch):
    """Clone into tmp with the pinned identity and switch to a new branch; return a runner bound to tmp."""
    run = lambda *a: subprocess.run(a, cwd=tmp, check=True)
    subprocess.run(["gh", "repo", "clone", repo, tmp], check=True)
    run("git", "config", "user.name", IDENTITY[0])
    run("git", "config", "user.email", IDENTITY[1])
    run("git", "checkout", "-b", branch)
    return run


def _write_claude_md(tmp, block):
    """Create CLAUDE.md from the template if missing, then upsert the disciplines block. True if changed."""
    path = pathlib.Path(tmp) / "CLAUDE.md"
    before = path.read_text() if path.exists() else None
    base = before if before is not None else (HERE / "repo" / "CLAUDE.md.tmpl").read_text()
    after = disciplines.upsert_block(base, block)
    if after == before:
        return False
    path.write_text(after)
    return True


def _onboard_files(repo, tier, block):
    with tempfile.TemporaryDirectory() as tmp:
        run = _clone_on_branch(repo, tmp, "chore/claude-baseline")
        if _write_claude_md(tmp, block):
            run("git", "add", "CLAUDE.md")
        if WORKFLOW in files_for_tier(tier):
            dst = pathlib.Path(tmp) / WORKFLOW
            if dst.exists():
                print(f"skip {WORKFLOW}: already exists")
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text((HERE / "repo" / "delete-unmerged-pr-branch.yml").read_text())
                run("git", "add", WORKFLOW)
        run("git", "commit", "-m", "chore: add Claude baseline files")
        run("git", "push", "-u", "origin", "chore/claude-baseline")
        run("gh", "pr", "create", "--title", "chore: add Claude baseline files",
            "--body", "Adds baseline CLAUDE.md (with the agentic-sdlc disciplines block) and, on the "
                      "standard tier, the branch-cleanup workflow. Config only; no test runner.")


def refresh_disciplines(repo, block):
    """Open a PR that brings the repo's disciplines block up to date. False if it already was."""
    branch = "chore/agentic-sdlc-disciplines"
    with tempfile.TemporaryDirectory() as tmp:
        run = _clone_on_branch(repo, tmp, branch)
        if not _write_claude_md(tmp, block):
            print(f"{repo}: disciplines block already current")
            return False
        run("git", "add", "CLAUDE.md")
        run("git", "commit", "-m", "chore: refresh agentic-sdlc disciplines block in CLAUDE.md")
        run("git", "push", "-u", "origin", branch)
        run("gh", "pr", "create", "--title", "chore: refresh agentic-sdlc disciplines block",
            "--body", "Regenerates the marker-delimited disciplines block in CLAUDE.md from "
                      "jasoncookdesign/agentic-sdlc. Generated config; no test runner.")
        return True


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--tier", choices=TIERS)
    mode.add_argument("--disciplines", action="store_true",
                      help="only refresh the agentic-sdlc disciplines block in CLAUDE.md")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    sources, sha = disciplines.fetch_sources()
    block = disciplines.render_block(sources, sha)
    if a.disciplines:
        print(f"refresh disciplines block in {a.repo}/CLAUDE.md from agentic-sdlc @{sha[:7]}")
        if not a.apply:
            print("(dry run; pass --apply to execute)")
            return 0
        refresh_disciplines(a.repo, block)
        return 0
    calls = repo_settings_calls(a.repo, a.tier)
    for c in calls:
        print(describe_call(c))
    print("files:", ", ".join(files_for_tier(a.tier)), f"(CLAUDE.md gets the disciplines block @{sha[:7]})")
    if not a.apply:
        print("(dry run; pass --apply to execute)")
        return 0
    for c in calls:
        subprocess.run(gh_argv(c), input=json.dumps(c["body"]) if "body" in c else None,
                       text=True, check=True)
    _onboard_files(a.repo, a.tier, block)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
