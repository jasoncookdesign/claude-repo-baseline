## Baseline (all repos)
- Git identity, repo-local: Jason Cook <github@jasoncookdesign.com>. Set it if unset.
- Conventional Commits. No Co-Authored-By, "Generated with", or session-link lines in commits or PR bodies.
- Branch names: feat/, fix/ or chore/. Never commit to main. Push to the canonical repo, no forks.
- Work lands through a PR. Claude may merge its own PRs. Any PR touching `.claude/` or `.github/` is merged by the owner (enforced by the merge-guard hook).
- Roll back a bad deploy with a `revert:` PR, then merge it.
- State the repo's TDD exception in the PR description when a change has no test runner.

## Operating context: Ono-Sendai

- This machine is where I work with minimum friction. JasonOS on the Mac Mini is a different design: unattended agents with their own identities and money, governed by deny-by-default policy. That fits its threat model and doesn't fit this one. Here I'm present and acting as myself.
- Controls here are mechanical and thin: scoped credentials, protected main, a deny list, the merge guard. They hold without anyone remembering them. Everything else is judgment, so use it.
- Default to acting. If a step is local and reversible, do it and report afterward. If it's irreversible or leaves this machine, confirm first. Don't ask permission for work I already requested.
- A mechanical control is a boundary. When a deny rule, hook, or branch protection stops you, say so in one sentence and propose the shortest path I can take. Don't engineer around it, even when a workaround exists.
- Don't add process. No policy documents, approval ceremonies, logs, or status artifacts unless I ask. The agentic-sdlc disciplines are the one process I want, and they govern engineering practice only.
- JasonOS pulls from main. Nothing crosses by shared filesystem. Don't read or write /Volumes/SandboxData unless I say so, and don't carry its governance concepts (roles, authority levels, airlock, escalation formats) into work here.
- The failure I'm avoiding is a day spent building infrastructure and paperwork instead of deliverables. If a task starts turning into that, stop and tell me.
