# claude-repo-baseline

Baseline Claude Code config for personal repos.

- `python3 install_user.py [--dry-run]` merges `user/` into `~/.claude` (deny rules, merge-guard hook, CLAUDE.md block) and copies `skills/` (the `onboard-repo` skill). Idempotent; writes `.bak` files.
- `python3 bootstrap.py OWNER/REPO --tier live|private|scratch [--apply]` sets repo settings and opens a PR with `CLAUDE.md` and the branch-cleanup workflow. Dry run by default.
- `hooks/guard_merge.py` refuses merges of PRs that touch `.claude/` or `.github/`.
- Tests: `python3 -m unittest discover -s tests`
