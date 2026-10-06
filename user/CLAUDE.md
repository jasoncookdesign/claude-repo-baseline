## Baseline (all repos)
- Git identity, repo-local: Jason Cook <github@jasoncookdesign.com>. Set it if unset.
- Conventional Commits. No Co-Authored-By, "Generated with", or session-link lines in commits or PR bodies.
- Branch names: feat/, fix/ or chore/. Never commit to main. Push to the canonical repo, no forks.
- Work lands through a PR. Claude may merge its own PRs. Any PR touching `.claude/` or `.github/` is merged by the owner (enforced by the merge-guard hook).
- Roll back a bad deploy with a `revert:` PR, then merge it.
- State the repo's TDD exception in the PR description when a change has no test runner.
