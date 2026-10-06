---
name: onboard-repo
description: Use when starting or onboarding a git repo (new project, "set up this repo", "initialize repo", a new Claude Project for a repo) to apply the personal baseline from claude-repo-baseline: repo settings, main protection, CLAUDE.md (with the agentic-sdlc disciplines block) and the branch-cleanup workflow. Also use to refresh a repo's disciplines block after agentic-sdlc changes.
---

# Onboard a repo

The baseline lives in the `claude-repo-baseline` repo (jasoncookdesign). Its `bootstrap.py` does the work; this skill is the order of operations and the traps.

## 1. Preconditions (on the Mac, once per machine)
- Baseline installed: `~/.claude/hooks/guard_merge.py` exists. If not, run `python3 install_user.py` from a clone of `claude-repo-baseline`.
- `gh auth status` shows "Git operations protocol: https". If it shows ssh, fix the per-host setting: `gh config set -h github.com git_protocol https` then `gh auth setup-git`. The global `gh config set git_protocol` is not enough.
- The token has the `workflow` scope, or the push of `.github/workflows/` is rejected: `gh auth refresh -s workflow`.

## 2. Pick a tier
- `standard`: protects main (0 approvals, admins enforced, no force push), adds the cleanup workflow and `CLAUDE.md`. Use for anything real, deployed or not.
- `scratch`: settings and `CLAUDE.md` only, no protection, no workflow. Use for throwaway repos.
Whether merging deploys is recorded in the repo's `CLAUDE.md`, not in the tier. If it is unclear, ask.
Private repos on GitHub Free can't have branch protection, so use `scratch` for them. The local deny list still blocks pushes to main.

## 3. Dry run, then apply
`python3 bootstrap.py OWNER/REPO --tier TIER` prints the plan. Show it, get a go-ahead, then re-run with `--apply`. It sets delete-branch-on-merge and auto-merge off, protects main (0 approvals, admins enforced, no force push), clones to a temp dir and opens a `chore/claude-baseline` PR. An existing `CLAUDE.md` is kept, with the disciplines block appended. A missing one is created from the template, block included.

## 4. After
- That PR touches `.github/`, so the owner merges it, not Claude.
- Fill in the repo's `CLAUDE.md` specifics: what merging does, generated paths never hand-edited, the TDD exception. Keep it short.
- Verify protection: `gh api repos/OWNER/REPO/branches/main/protection --jq '{enforce_admins: .enforce_admins.enabled, approvals: .required_pull_request_reviews.required_approving_review_count, force_push: .allow_force_pushes.enabled}'` should give true, 0, false.
- Delete any stray branches.

## Disciplines block
`CLAUDE.md` carries a marker-delimited block generated from `jasoncookdesign/agentic-sdlc` (disciplines plus repository hygiene) and pinned to one commit. A repo's `CLAUDE.md` is the one instruction file that every session loads, cloud and scheduled sessions included, so this is how the disciplines travel. Never hand-edit the block. Change agentic-sdlc, then refresh:
`python3 bootstrap.py OWNER/REPO --disciplines` (dry run), then `--apply`. That opens a `chore/agentic-sdlc-disciplines` PR, or does nothing if the block is already current. It only touches `CLAUDE.md`, so Claude may merge it.

## Rules this sets up
Claude merges its own PRs except those touching `.claude/` or `.github/` (enforced by the guard hook). Never commit or force-push to main. Roll back with a `revert:` PR.
