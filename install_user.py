#!/usr/bin/env python3
"""Install the baseline into ~/.claude: merge settings, hooks, and CLAUDE.md block.

Idempotent. Existing keys and rules are kept; backups are written as *.bak.
Usage: python3 install_user.py [--dry-run]
"""
import copy
import json
import pathlib
import shutil
import sys

BEGIN = "<!-- BEGIN claude-repo-baseline -->"
END = "<!-- END claude-repo-baseline -->"
HERE = pathlib.Path(__file__).resolve().parent


def _fill(obj, hooks_dir):
    if isinstance(obj, str):
        return obj.replace("{HOOKS_DIR}", hooks_dir)
    if isinstance(obj, list):
        return [_fill(x, hooks_dir) for x in obj]
    if isinstance(obj, dict):
        return {k: _fill(v, hooks_dir) for k, v in obj.items()}
    return obj


def merge_settings(existing, template, hooks_dir):
    """Merge the template into existing settings; {HOOKS_DIR} becomes the installed hooks folder."""
    out = copy.deepcopy(existing)
    tpl = _fill(template, hooks_dir)
    deny = out.setdefault("permissions", {}).setdefault("deny", [])
    for rule in tpl.get("permissions", {}).get("deny", []):
        if rule not in deny:
            deny.append(rule)
    for event, entries in tpl.get("hooks", {}).items():
        have = out.setdefault("hooks", {}).setdefault(event, [])
        for entry in entries:
            if entry not in have:
                have.append(entry)
    return out


def merge_claude_md(existing, block):
    body = f"{BEGIN}\n{block.strip()}\n{END}\n"
    if BEGIN in existing and END in existing:
        head, _, rest = existing.partition(BEGIN)
        _, _, tail = rest.partition(END)
        return head + body.rstrip("\n") + tail
    sep = "" if not existing or existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    return existing + sep + body


def hook_targets(src_root, dst_root):
    """(src, dst) pairs for every hook script in src_root."""
    return [(f, dst_root / f.name) for f in sorted(src_root.glob("*.py"))]


def skill_targets(src_root, dst_root):
    """(src, dst) pairs for every file under src_root/<skill>/."""
    if not src_root.is_dir():
        return []
    pairs = []
    for f in sorted(src_root.glob("*/**/*")):
        if f.is_file():
            pairs.append((f, dst_root / f.relative_to(src_root)))
    return pairs


def _backup(path):
    if path.exists():
        shutil.copy2(path, str(path) + ".bak")


def main(argv):
    dry = "--dry-run" in argv
    home = pathlib.Path.home() / ".claude"
    hooks_dst = home / "hooks"
    settings_p, md_p = home / "settings.json", home / "CLAUDE.md"
    tpl = json.loads((HERE / "user" / "settings.json").read_text())
    existing = json.loads(settings_p.read_text()) if settings_p.exists() else {}
    merged = merge_settings(existing, tpl, str(hooks_dst))
    md = merge_claude_md(md_p.read_text() if md_p.exists() else "",
                         (HERE / "user" / "CLAUDE.md").read_text())
    if dry:
        print(json.dumps(merged, indent=2))
        print("--- CLAUDE.md ---")
        print(md)
        return 0
    home.mkdir(exist_ok=True)
    hooks_dst.mkdir(exist_ok=True)
    for src, dst in hook_targets(HERE / "hooks", hooks_dst):
        shutil.copy2(src, dst)
    for src, dst in skill_targets(HERE / "skills", home / "skills"):
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    _backup(settings_p)
    settings_p.write_text(json.dumps(merged, indent=2) + "\n")
    _backup(md_p)
    md_p.write_text(md)
    print(f"Installed to {home}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
