#!/usr/bin/env python3
"""Onboard one repo: apply GitHub repo settings and open a PR with the baseline files.

Usage: python3 bootstrap.py OWNER/REPO --tier live|private|scratch [--apply]
Default is a dry run that prints the plan. Needs `gh` authenticated locally.
Tiers: live = deploys on merge (protect main); private = settings only, no deploy;
scratch = settings only, no protection and no workflow.
"""
import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TIERS = ("live", "private", "scratch")
WORKFLOW = ".github/workflows/delete-unmerged-pr-branch.yml"


def _validate(repo, tier):
    if repo.count("/") != 1 or not all(repo.split("/")):
        raise ValueError(f"repo must be OWNER/REPO, got {repo!r}")
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}, got {tier!r}")


def repo_settings_calls(repo, tier):
    _validate(repo, tier)
    calls = [{"method": "PATCH", "path": f"repos/{repo}",
              "fields": {"delete_branch_on_merge": True, "allow_auto_merge": False}}]
    if tier in ("live", "private"):
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


def _onboard_files(repo, tier):
    src = {"CLAUDE.md": HERE / "repo" / "CLAUDE.md.tmpl", WORKFLOW: HERE / "repo" / "delete-unmerged-pr-branch.yml"}
    with tempfile.TemporaryDirectory() as tmp:
        run = lambda *a: subprocess.run(a, cwd=tmp, check=True)
        subprocess.run(["gh", "repo", "clone", repo, tmp], check=True)
        run("git", "checkout", "-b", "chore/claude-baseline")
        for rel in files_for_tier(tier):
            dst = pathlib.Path(tmp) / rel
            if dst.exists():
                print(f"skip {rel}: already exists")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(src[rel].read_text())
            run("git", "add", rel)
        run("git", "commit", "-m", "chore: add Claude baseline files")
        run("git", "push", "-u", "origin", "chore/claude-baseline")
        run("gh", "pr", "create", "--title", "chore: add Claude baseline files",
            "--body", "Adds baseline CLAUDE.md and branch-cleanup workflow. Config only; no test runner.")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--tier", required=True, choices=TIERS)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    calls = repo_settings_calls(a.repo, a.tier)
    for c in calls:
        print(" ".join(gh_argv(c)))
    print("files:", ", ".join(files_for_tier(a.tier)))
    if not a.apply:
        print("(dry run; pass --apply to execute)")
        return 0
    for c in calls:
        subprocess.run(gh_argv(c), input=json.dumps(c["body"]) if "body" in c else None,
                       text=True, check=True)
    _onboard_files(a.repo, a.tier)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
