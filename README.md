# claude-repo-baseline

Baseline Claude Code config for personal repos.

- `python3 install_user.py [--dry-run]` merges `user/` into `~/.claude` (deny rules, merge-guard hook, CLAUDE.md block) and copies `skills/` (the `onboard-repo` skill). Idempotent; writes `.bak` files.
- `python3 bootstrap.py OWNER/REPO --tier standard|scratch [--apply]` sets repo settings and opens a PR with `CLAUDE.md` and the branch-cleanup workflow. `CLAUDE.md` gets a marker-delimited block of the agentic-sdlc disciplines, fetched from `jasoncookdesign/agentic-sdlc` at its current `main` commit, so the disciplines load in every session, cloud included. An existing `CLAUDE.md` is kept, with the block added.
- `python3 bootstrap.py OWNER/REPO --disciplines [--apply]` refreshes only that block, opening a `chore/agentic-sdlc-disciplines` PR, or nothing when it's already current. The rendering lives in `disciplines.py`. Commits in the clone use a pinned identity (Jason Cook, github@jasoncookdesign.com), not the global git config. Dry run by default.
- `hooks/guard_merge.py` refuses merges of PRs that touch `.claude/` or `.github/`.
- Tests: `python3 -m unittest discover -s tests`
